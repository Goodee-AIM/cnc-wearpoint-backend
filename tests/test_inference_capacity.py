from app.api.routers import auto_prediction
from app.services import inference_capacity, monitoring_inference_queue


def test_manual_and_monitoring_slots_are_independent():
    assert auto_prediction._inference_slots is inference_capacity.manual_inference_slots
    assert monitoring_inference_queue.inference_slots is inference_capacity.monitoring_inference_slots
    assert auto_prediction._inference_slots is not monitoring_inference_queue.inference_slots


def test_busy_monitoring_slot_does_not_block_manual_slot():
    monitoring = inference_capacity.monitoring_inference_slots
    manual = inference_capacity.manual_inference_slots
    assert monitoring.acquire(blocking=False)
    try:
        assert manual.acquire(blocking=False)
        manual.release()
    finally:
        monitoring.release()
