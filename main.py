from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
import os, datetime, time, threading, httpx
from pymongo import MongoClient
from bson.objectid import ObjectId
from dotenv import load_dotenv

load_dotenv()
MONGODB_URI = os.environ.get("MONGODB_URI")
if not MONGODB_URI:
    raise Exception("Missing MONGODB_URI environment variable")

client = MongoClient(MONGODB_URI)
db = client["PyHit"]
collection = db["links"]

app = FastAPI()
<<<<<<< HEAD
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))
=======
templates = Jinja2Templates(directory="templates")
>>>>>>> 66760937412869cace5e09292c407b71cc89f4c9

def load_links():
    docs = list(collection.find({}))
    for d in docs:
        d["_id"] = str(d["_id"])
    return docs

def add_link(name, url, start, end, end_date):
    if not name.strip():
        name = url
    new_link = {
        "name": name,
        "url": url,
        "start": int(start),
        "end": int(end),
        "end_date": end_date.isoformat() if end_date else None
    }
    collection.replace_one({"url": url}, new_link, upsert=True)

def delete_link_by_id(link_id: str):
    collection.delete_one({"_id": ObjectId(link_id)})

def pinger():
    while True:
        now = datetime.datetime.now()
        hr = now.hour
        docs = list(collection.find({}))
        for l in docs:
            if l.get("end_date"):
                try:
                    exp_date = datetime.date.fromisoformat(l["end_date"])
                    expiry_dt = datetime.datetime.combine(exp_date + datetime.timedelta(days=1), datetime.time())
                    if now >= expiry_dt:
                        collection.delete_one({"_id": l["_id"]})
                        print("Expired and removed:", l)
                except Exception as e:
                    print("Error parsing end_date for", l, ":", e)
        docs = list(collection.find({}))
        with httpx.Client() as client:
            for l in docs:
                if l["start"] <= hr < l["end"]:
                    try:
                        client.head(l["url"], timeout=10)
                    except Exception as e:
                        print("Error pinging", l["url"], ":", e)
        time.sleep(60)

def start_pinger():
    threading.Thread(target=pinger, daemon=True).start()

@app.on_event("startup")
def startup_event():
    start_pinger()

@app.get("/", response_class=HTMLResponse)
def read_index(request: Request):
    links = load_links()
    return templates.TemplateResponse("index.html", {"request": request, "links": links})

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
    if eternal == "on":
        end_date_obj = None
    else:
        end_date_obj = datetime.datetime.strptime(end_date, "%Y-%m-%d").date() if end_date else None
    add_link(name, url, start, end, end_date_obj)
    return RedirectResponse(url="/", status_code=303)

@app.post("/delete")
def delete_link_endpoint(link_id: str = Form(...)):
    delete_link_by_id(link_id)
    return RedirectResponse(url="/", status_code=303)