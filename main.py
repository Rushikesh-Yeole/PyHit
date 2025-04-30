from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
import os, datetime, time, threading, httpx
from pymongo import MongoClient
from bson.objectid import ObjectId
from dotenv import load_dotenv
from zoneinfo import ZoneInfo  # For IST

load_dotenv()
MONGODB_URI = os.environ.get("MONGODB_URI")
if not MONGODB_URI:
    raise Exception("Missing MONGODB_URI environment variable")

client = MongoClient(MONGODB_URI)
db = client["PyHit"]
collection = db["links"]

app = FastAPI()
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))

def load_links(expired: bool = False):
    query = {"expired": True} if expired else {"expired": {"$ne": True}}
    docs = list(collection.find(query))
    for d in docs:
        d["_id"] = str(d["_id"])
    return docs

def add_link(name, url, start, end, end_date):
    name = name.strip() or url
    # If an end date is provided, store it as ISO string; otherwise, keep as None.
    stored_end_date = end_date.isoformat() if end_date else None
    expired = False
    if end_date:
        exp_dt = datetime.datetime.combine(end_date + datetime.timedelta(days=1), datetime.time()).replace(tzinfo=ZoneInfo("Asia/Kolkata"))
        expired = datetime.datetime.now(ZoneInfo("Asia/Kolkata")) >= exp_dt
    collection.replace_one(
        {"url": url},
        {"name": name, "url": url, "start": int(start), "end": int(end), "end_date": stored_end_date, "expired": expired},
        upsert=True
    )

def delete_link_by_id(link_id: str):
    collection.delete_one({"_id": ObjectId(link_id)})

def pinger():
    while True:
        now = datetime.datetime.now(ZoneInfo("Asia/Kolkata"))
        hr = now.hour
        # Mark expired links without deleting them.
        for l in collection.find({"end_date": {"$exists": True, "$ne": None}}):
            try:
                exp_date = datetime.date.fromisoformat(l["end_date"])
                expiry_dt = datetime.datetime.combine(exp_date + datetime.timedelta(days=1), datetime.time()).replace(tzinfo=ZoneInfo("Asia/Kolkata"))
                if now >= expiry_dt and not l.get("expired", False):
                    collection.update_one({"_id": l["_id"]}, {"$set": {"expired": True}})
                    print("Marked as expired:", l["name"])
            except Exception as e:
                print("Error parsing end_date for", l, ":", e)
        # Ping active links.
        with httpx.Client() as client:
            for l in collection.find({"expired": {"$ne": True}}):
                if l["start"] <= hr <= l["end"]:
                    try:
                        resp = client.get(l["url"], timeout=10)
                        print(f"Pinged {l['url']} with status: {resp.status_code}")
                    except Exception as e:
                        print(f"Error pinging {l['url']}: {e}")
        time.sleep(60)

def start_pinger():
    threading.Thread(target=pinger, daemon=True).start()

@app.on_event("startup")
def startup_event():
    start_pinger()

@app.head("/")
def head():
    return ""

@app.get("/", response_class=HTMLResponse)
def read_index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "links": load_links(False)})

@app.get("/expired", response_class=HTMLResponse)
def read_expired(request: Request):
    return templates.TemplateResponse("expired.html", {"request": request, "links": load_links(True)})

@app.post("/add")
def add_link_endpoint(
    request: Request,
    name: str = Form(...),
    url: str = Form(...),
    start: int = Form(...),
    end: int = Form(...),
    eternal: str = Form(None),
    end_date: str = Form(None)
):
    date_obj = None if eternal == "on" else (datetime.datetime.strptime(end_date, "%Y-%m-%d").date() if end_date else None)
    add_link(name, url, start, end, date_obj)
    return RedirectResponse(url="/", status_code=303)

@app.post("/delete")
def delete_link_endpoint(link_id: str = Form(...)):
    delete_link_by_id(link_id)
    return RedirectResponse(url="/", status_code=303)
