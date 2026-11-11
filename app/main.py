import asyncio
import os
from contextlib import asynccontextmanager

from app.api.routers.monitoring_alerts import router as monitoring_alerts_router
from app.services.monitoring_alerts import run_alert_worker
from app.api.routers.monitoring import router as monitoring_router
from app.api.routers.alerts import router as alerts_router
from app.api.routers.sets import router as sets_router
from app.api.routers.sensors import router as sensors_router

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers.health import router as health_router
from app.api.routers.images import router as images_router

from app.core.config import get_cors_origins


@asynccontextmanager
async def lifespan(app):
    stop = asyncio.Event()
    worker = None
    if os.getenv("MONITORING_ALERT_WORKER_ENABLED", "1") == "1":
        worker = asyncio.create_task(run_alert_worker(stop))
    try:
        yield
    finally:
        stop.set()
        if worker is not None:
            await worker


app = FastAPI(title="CNC WearPoint API", lifespan=lifespan)

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

app.include_router(monitoring_router)

app.include_router(monitoring_alerts_router)
