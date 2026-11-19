"""전달받은 전처리 기준으로 원본 센서의 절삭 구간 경계를 계산합니다."""
from io import BytesIO

import numpy as np
import pandas as pd
from scipy.ndimage import uniform_filter1d

CUT_WINDOW_MS = 50
CUT_MIN_DURATION_MS = 100


def extract_cutting_segment(df, fs, window_ms=CUT_WINDOW_MS,
                            min_duration_ms=CUT_MIN_DURATION_MS):
    if len(df) == 0:
        raise ValueError("센서 데이터가 비어 있습니다.")
    fx = df["force_x"].to_numpy(dtype=np.float64)
    fy = df["force_y"].to_numpy(dtype=np.float64)
    if not np.isfinite(fx).all() or not np.isfinite(fy).all():
        raise ValueError("Force X/Y에 NaN 또는 무한대 값이 포함되어 있습니다.")
    baseline_n = max(1, int(len(df) * 0.1))
    fx = fx - np.median(fx[:baseline_n])
    fy = fy - np.median(fy[:baseline_n])
    window = max(1, int(round(fs * window_ms / 1000)))
    rms_x = np.sqrt(uniform_filter1d(fx ** 2, size=window, mode="reflect"))
    rms_y = np.sqrt(uniform_filter1d(fy ** 2, size=window, mode="reflect"))
    energy = np.sqrt(rms_x ** 2 + rms_y ** 2)
    baseline_energy = energy[energy <= np.percentile(energy, 20)]
    noise_median = float(np.median(baseline_energy))
    mad = float(np.median(np.abs(baseline_energy - noise_median)))
    noise_std = 1.4826 * mad
    low_threshold = noise_median + 6 * noise_std
    high_threshold = noise_median + 10 * noise_std
    active = False
    mask = np.zeros(len(df), dtype=bool)
    for i, value in enumerate(energy):
        if not active and value > high_threshold:
            active = True
        elif active and value < low_threshold:
            active = False
        mask[i] = active
    changes = np.diff(np.r_[False, mask, False].astype(np.int8))
    starts = np.where(changes == 1)[0]
    ends = np.where(changes == -1)[0]
    min_samples = max(1, int(round(fs * min_duration_ms / 1000)))
    valid_segments = [(int(start), int(end)) for start, end in zip(starts, ends)
                      if end - start >= min_samples]
    if not valid_segments:
        raise ValueError("최소 절삭구간 길이를 만족하는 구간을 찾지 못했습니다.")
    start_idx, end_idx = max(valid_segments, key=lambda segment: segment[1] - segment[0])
    return df.iloc[start_idx:end_idx].copy(), start_idx, end_idx


def describe_cutting_segment(csv_bytes):
    df = pd.read_csv(BytesIO(csv_bytes), header=None)
    if df.shape[1] != 6 or df.empty:
        raise ValueError("센서 CSV는 비어 있지 않은 6열 데이터여야 합니다.")
    df.columns = ["acc", "audio", "force_x", "force_y", "force_z", "timestamp"]
    timestamp = pd.to_datetime(df["timestamp"], format="mixed", errors="coerce")
    if timestamp.isna().any():
        raise ValueError("파싱할 수 없는 timestamp가 있습니다.")
    intervals_sec = timestamp.diff().dt.total_seconds().iloc[1:].to_numpy(dtype=np.float64)
    intervals_sec = intervals_sec[np.isfinite(intervals_sec) & (intervals_sec > 0)]
    if intervals_sec.size == 0:
        raise ValueError("유효한 timestamp 간격을 계산할 수 없습니다.")
    median_dt_sec = float(np.median(intervals_sec))
    fs_hz = 1.0 / median_dt_sec
    _, start_idx, end_idx = extract_cutting_segment(df, fs=fs_hz)
    # 나노초 정밀도를 유지한 Python 시각으로 경계를 전달합니다.
    origin = timestamp.iloc[0]
    start_seconds = (timestamp.iloc[start_idx] - origin).value / 1e9
    if end_idx < len(df):
        end_seconds = (timestamp.iloc[end_idx] - origin).value / 1e9
    else:
        end_seconds = (timestamp.iloc[-1] - origin).value / 1e9 + median_dt_sec
    return {
        "status": "ok", "start_idx": start_idx, "end_idx": end_idx,
        "start_seconds": start_seconds, "end_seconds": end_seconds,
        "fs_hz": fs_hz, "window_ms": CUT_WINDOW_MS,
        "min_duration_ms": CUT_MIN_DURATION_MS,
    }
