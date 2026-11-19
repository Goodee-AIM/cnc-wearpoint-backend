"""Read-only replay inference status. Never returns stale measurement results."""
import os
from fastapi import APIRouter, HTTPException
from app.services.monitoring_inference_queue import current_runs

router = APIRouter(prefix='/api/monitoring/inference', tags=['replay-inference'])

@router.get('/current')
def get_current_inference_runs():
    if os.getenv('MONITORING_INFERENCE_ENABLED', '0') != '1':
        raise HTTPException(503, 'Replay inference is disabled')
    return current_runs()
