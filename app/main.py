import asyncio
import os
from contextlib import asynccontextmanager

from app.api.routers.monitoring_alerts import router as monitoring_alerts_router
from app.api.routers.historical_reinfer import router as historical_reinfer_router
from app.services.monitoring_alerts import run_alert_worker
from app.api.routers.monitoring import router as monitoring_router
from app.api.routers.monitoring_inference import router as monitoring_inference_router
from app.services.monitoring_inference_queue import run_inference_worker
from app.api.routers.alerts import router as alerts_router
from app.api.routers.sets import router as sets_router
from app.api.routers.sensors import router as sensors_router

from app.api.routers.measurements import router as measurements_router
from app.api.routers.auto_prediction import router as auto_prediction_router
from app.api.routers.predictions import (
    router as predictions_router,
    auth_router as prediction_auth_router,
)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers.health import router as health_router
from app.api.routers.images import router as images_router

from app.api.routers.manual_inputs import router as manual_inputs_router
from app.core.config import get_cors_origins


@asynccontextmanager
async def lifespan(app):
    if (os.getenv('MONITORING_INFERENCE_ENABLED', '0') == '1'
            and os.getenv('MONITORING_ALERT_WORKER_ENABLED', '1') == '1'):
        raise RuntimeError('Gated replay requires disabling the legacy global-clock alert worker until occurrence-aware alerts are integrated.')
    stop = asyncio.Event()
    worker = None
    inference_worker = None
    if os.getenv("MONITORING_INFERENCE_ENABLED", "0") == "1":
        inference_worker = asyncio.create_task(run_inference_worker(stop))
    if os.getenv("MONITORING_ALERT_WORKER_ENABLED", "1") == "1":
        worker = asyncio.create_task(run_alert_worker(stop))
    try:
        yield
    finally:
        stop.set()
        if worker is not None:
            await worker
        if inference_worker is not None:
            await inference_worker


app = FastAPI(title="CNC WearPoint API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_origins(),
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=["Content-Type", "X-Monitoring-Control-Token"],
    allow_credentials=False,
)

app.include_router(health_router)
app.include_router(images_router)
app.include_router(sets_router)
app.include_router(sensors_router)
app.include_router(alerts_router)

app.include_router(monitoring_router)
app.include_router(monitoring_inference_router)

app.include_router(monitoring_alerts_router)
app.include_router(historical_reinfer_router)

app.include_router(manual_inputs_router)

app.include_router(measurements_router)
app.include_router(auto_prediction_router)
app.include_router(prediction_auth_router)
app.include_router(predictions_router)
