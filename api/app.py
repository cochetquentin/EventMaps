from fastapi import FastAPI

from api.routes.events import router

app = FastAPI(title="EventMaps API", version="0.1.0")
app.include_router(router, prefix="/events", tags=["events"])
