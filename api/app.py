import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from api.limiter import limiter
from api.routes.events import router
from api.routes.scrape import router as scrape_router
from config import settings
from db.store import EventStore

logging.basicConfig(
    level=settings.log_level.upper(),
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)

app = FastAPI(title="EventMaps API", version="0.1.0")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router, prefix="/events", tags=["events"])
app.include_router(scrape_router, prefix="/scrape", tags=["scrape"])
app.mount("/js", StaticFiles(directory="frontend/js"), name="js")


@app.get("/")
def index():
    return FileResponse("frontend/index.html")


@app.get("/health", tags=["meta"])
def health():
    with EventStore(settings.db_path) as store:
        store._conn.execute("SELECT 1")
    return {"status": "ok"}
