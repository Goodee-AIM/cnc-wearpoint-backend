"""Convert a paired raw MATWI image and sensor CSV into model inputs."""
import numpy as np
import pandas as pd
import torch
from numpy.lib.stride_tricks import sliding_window_view
from PIL import Image
from scipy.ndimage import uniform_filter1d
from torchvision import transforms

SENSOR_COLUMNS = ["acc", "audio", "force_x", "force_y", "force_z", "timestamp"]


def extract_cutting_segment(
    df,
    fs=1617,
    window_ms=50,
    min_duration_ms=100,
):
    """Fx와 Fy의 결합 이동 RMS로 가장 긴 절삭 구간을 추출한다."""
    fx = df["force_x"].to_numpy(dtype=float)
    fy = df["force_y"].to_numpy(dtype=float)

    # 1. 처음 10% 구간의 중앙값으로 baseline 추정
    baseline_n = int(len(df) * 0.1)
    base_x = np.median(fx[:baseline_n])
    base_y = np.median(fy[:baseline_n])

    fx = fx - base_x
    fy = fy - base_y

    # 2. 채널별 이동 RMS 계산 후 결합
    window = max(1, int(fs * window_ms / 1000))
    rms_x = np.sqrt(uniform_filter1d(fx**2, size=window))
    rms_y = np.sqrt(uniform_filter1d(fy**2, size=window))
    energy = np.sqrt(rms_x**2 + rms_y**2)

    # 3. 결합 RMS 하위 20%에서 잡음 수준과 임계값 계산
    baseline_energy = energy[energy <= np.percentile(energy, 20)]
    noise_median = np.median(baseline_energy)
    mad = np.median(np.abs(baseline_energy - noise_median))
    noise_std = 1.4826 * mad

    low_threshold = noise_median + 6 * noise_std
    high_threshold = noise_median + 10 * noise_std

    # 4. 높은 임계값을 넘으면 진입, 낮은 임계값 아래로 내려가면 이탈
    active = False
    mask = np.zeros(len(df), dtype=bool)

    for i, value in enumerate(energy):
        if not active and value > high_threshold:
            active = True
        elif active and value < low_threshold:
            active = False

        mask[i] = active

    # 5. 최소 길이를 충족하는 연속 구간 중 가장 긴 구간 선택
    changes = np.diff(np.r_[False, mask, False].astype(int))
    starts = np.where(changes == 1)[0]
    ends = np.where(changes == -1)[0]

    if len(starts) == 0:
        raise ValueError("절삭 구간을 검출하지 못했습니다.")

    min_samples = int(fs * min_duration_ms / 1000)
    valid = [
        (start, end)
        for start, end in zip(starts, ends)
        if end - start >= min_samples
    ]

    if not valid:
        raise ValueError("유효한 절삭 구간이 없습니다.")

    start, end = max(valid, key=lambda segment: segment[1] - segment[0])
    cutting_df = df.iloc[start:end].copy()

    return cutting_df, energy, start, end, (
        low_threshold,
        high_threshold,
    )


def read_and_cut_sensor(csv_path):
    df = pd.read_csv(csv_path, header=None)

    if df.shape[1] != 6:
        raise ValueError(f"센서 CSV는 6열이어야 합니다. 실제 열 수: {df.shape[1]}")

    df.columns = SENSOR_COLUMNS
    sensor_columns = SENSOR_COLUMNS[:-1]
    df[sensor_columns] = df[sensor_columns].apply(pd.to_numeric, errors="coerce")

    if not np.isfinite(df[sensor_columns].to_numpy()).all():
        raise ValueError("센서 값에 결측값, 파싱 실패 또는 무한대가 있습니다.")

    timestamp = pd.to_datetime(df["timestamp"], format="mixed", errors="coerce")
    if timestamp.isna().any():
        raise ValueError("파싱할 수 없는 timestamp가 있습니다.")

    intervals_sec = timestamp.diff().dt.total_seconds().iloc[1:].to_numpy()
    if intervals_sec.size == 0 or not np.all(intervals_sec > 0):
        raise ValueError("timestamp 간격이 없거나, 시각이 중복·역행합니다.")

    median_dt_sec = float(np.median(intervals_sec))
    if not np.allclose(intervals_sec, median_dt_sec, atol=1e-9, rtol=0):
        raise ValueError("파일 내 timestamp 간격이 일정하지 않습니다.")

    fs_hz = 1.0 / median_dt_sec
    cutting_df, _, start_idx, end_idx, _ = extract_cutting_segment(df, fs=fs_hz)

    return cutting_df, fs_hz, start_idx, end_idx


def hampel_filter(signal, window_size=21, n_sigmas=4):
    signal = np.asarray(signal, dtype=np.float64)

    if window_size % 2 == 0:
        raise ValueError("Window size must be odd.")

    half_window = window_size // 2
    padded = np.pad(signal, (half_window, half_window), mode="reflect")
    windows = sliding_window_view(padded, window_size)

    local_median = np.median(windows, axis=1)
    deviations = np.abs(windows - local_median[:, None])
    local_mad = np.median(deviations, axis=1)

    robust_sigma = 1.4826 * local_mad
    threshold = n_sigmas * robust_sigma
    outlier_mask = np.abs(signal - local_median) > threshold

    filtered_signal = signal.copy()
    filtered_signal[outlier_mask] = local_median[outlier_mask]
    return filtered_signal, outlier_mask


def preprocess_image(path, crop, checkpoint):
    with Image.open(path) as source:
        image = source.convert("RGB")
        left, top, right, bottom = crop
        if not (0 <= left < right <= image.width and 0 <= top < bottom <= image.height):
            raise ValueError(f"Crop {crop} is outside image bounds {image.size}.")
        image = image.crop(crop)
        transform = transforms.Compose([
            transforms.Resize(tuple(checkpoint["image_size"]), antialias=True),
            transforms.ToTensor(),
            transforms.Normalize(
                mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]
            ),
        ])
        return transform(image)


def preprocess_sensor(path, checkpoint):
    cutting, fs_hz, start, end = read_and_cut_sensor(path)
    signal = cutting[checkpoint["sensor_channel"]].to_numpy(dtype=np.float64)
    if checkpoint["use_hampel"]:
        signal, _ = hampel_filter(
            signal, checkpoint["hampel_window_size"], checkpoint["hampel_n_sigmas"]
        )
    rms_samples = max(1, int(fs_hz * (checkpoint["rms_window_ms"] / 1000)))
    rms = np.sqrt(np.maximum(
        uniform_filter1d(signal**2, size=rms_samples, mode="reflect"), 0.0
    ))
    size = int(checkpoint["window_size"])
    count = len(rms) // size
    if count == 0:
        raise ValueError(f"Detected cutting segment contains fewer than {size} samples.")
    mean, std = float(checkpoint["fy_mean"]), float(checkpoint["fy_std"])
    if not np.isfinite([mean, std]).all() or std <= 0:
        raise ValueError("Invalid training normalization statistics.")
    windows = (rms[:count * size].reshape(count, 1, size) - mean) / std
    return torch.from_numpy(windows.astype(np.float32)), (int(start), int(end)), fs_hz
