import logging
import time

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.middleware.base import BaseHTTPMiddleware

from api.limiter import limiter
from api.routes.events import router
from api.routes.scrape import router as scrape_router
from config import settings
from db.store import EventStore

logging.basicConfig(
    level=settings.log_level.upper(),
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)

_req_logger = logging.getLogger("api.requests")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        t0 = time.monotonic()
        response = await call_next(request)
        duration = time.monotonic() - t0
        _req_logger.info(
            "request method=%s path=%s status=%d duration=%.3fs",
            request.method,
            request.url.path,
            response.status_code,
            duration,
        )
        return response


app = FastAPI(title="EventMaps API", version="0.1.0")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)
if settings.request_logging:
    app.add_middleware(RequestLoggingMiddleware)
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
