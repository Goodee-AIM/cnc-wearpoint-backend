from app.api.routers.alerts import router as alerts_router
from app.api.routers.sets import router as sets_router
from app.api.routers.sensors import router as sensors_router

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers.health import router as health_router
from app.api.routers.images import router as images_router

from app.core.config import get_cors_origins
app = FastAPI(title="CNC WearPoint API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_origins(),
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=["Content-Type"],
    allow_credentials=False,
)

app.include_router(health_router)
app.include_router(images_router)
app.include_router(sets_router)
app.include_router(sensors_router)
app.include_router(alerts_router)
