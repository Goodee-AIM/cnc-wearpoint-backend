"""Shared in-process Serving capacity for upload and replay requests."""
from threading import BoundedSemaphore

inference_slots = BoundedSemaphore(1)
