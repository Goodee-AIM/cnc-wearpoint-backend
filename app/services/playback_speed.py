"""Replay source time at 4x; inference processing and result hold are unchanged."""
PLAYBACK_RATE = 4   
#그래프 속도 4배속 (공공Set)


def scaled_elapsed_ms(accumulated, started, now, *, rate=PLAYBACK_RATE):
    elapsed = int(accumulated)
    if started is not None:
        elapsed += max(0, int((now - started).total_seconds() * 1000 * rate))
    return elapsed
