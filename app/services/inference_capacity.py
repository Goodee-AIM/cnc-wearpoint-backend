"""In-process Serving capacity, split by caller.

Manual (Set test upload / replay / retry) and the Set4..Set11 monitoring
worker use separate slots so continuous monitoring inference never makes a
manual request fail with 429. At most one request of each kind reaches
Serving at a time from this process (i.e. up to 2 concurrent).
"""
from threading import BoundedSemaphore

# /auto-predict, /replay-predict, /retry
manual_inference_slots = BoundedSemaphore(1)

# Background monitoring inference worker (monitoring_inference_queue.process_one)
monitoring_inference_slots = BoundedSemaphore(1)
