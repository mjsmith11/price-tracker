import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.db import Base, engine
from app.routers import items, listings, search

logging.basicConfig(level=logging.INFO)

APP_DIR = Path(__file__).parent

app = FastAPI(title="Price Tracker")

Base.metadata.create_all(bind=engine)

app.include_router(items.router)
app.include_router(listings.router)
app.include_router(search.router)

app.mount("/static", StaticFiles(directory=APP_DIR / "static"), name="static")
templates = Jinja2Templates(directory=APP_DIR / "templates")


@app.get("/")
def dashboard(request: Request):
    return templates.TemplateResponse(request, "dashboard.html", {})


@app.get("/items/{item_id}")
def item_detail(request: Request, item_id: int):
    return templates.TemplateResponse(request, "item_detail.html", {"item_id": item_id})


@app.get("/healthz")
def healthz():
    return {"status": "ok"}
