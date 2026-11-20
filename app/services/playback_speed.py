"""Replay source time at 2x; inference processing and result hold are unchanged."""
PLAYBACK_RATE = 2


def scaled_elapsed_ms(accumulated, started, now, *, rate=PLAYBACK_RATE):
    elapsed = int(accumulated)
    if started is not None:
        elapsed += max(0, int((now - started).total_seconds() * 1000 * rate))
    return elapsed
