from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from api.routes.events import router
from api.routes.scrape import router as scrape_router

app = FastAPI(title="EventMaps API", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(router, prefix="/events", tags=["events"])
app.include_router(scrape_router, prefix="/scrape", tags=["scrape"])


@app.get("/")
def index():
    return FileResponse("frontend/index.html")
