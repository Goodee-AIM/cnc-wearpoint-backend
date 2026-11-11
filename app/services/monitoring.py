"""공통 재생의 고정 일정과 서버 시계 기반 현재 위치를 계산합니다."""
import csv
import math
from bisect import bisect_right
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

from app.services.storage import get_image_path


PHOTO_DURATION_MS = 2000


def sensor_duration(path: Path) -> int:
    """프런트 parseSensor와 같은 6열·시간순 검증을 적용합니다."""
    first_ms = None
    previous_ms = None
    with path.open(encoding="utf-8-sig", newline="") as source:
        for cells in csv.reader(source, strict=True):
            if not any(cell.strip() for cell in cells):
                continue
            if len(cells) != 6 or any(not cell.strip() for cell in cells[:5]):
                raise ValueError("센서 CSV는 숫자 5열과 시간 1열이어야 합니다.")
            if not all(math.isfinite(float(cell)) for cell in cells[:5]):
                raise ValueError("유효하지 않은 센서 값입니다.")
            # 프런트에서 사용하는 밀리초 정밀도와 동일하게 자릅니다.
            stamp = datetime.fromisoformat(cells[5].strip().replace(" ", "T")[:23])
            stamp = stamp.replace(tzinfo=timezone.utc)
            current_ms = round(stamp.timestamp() * 1000)
            if previous_ms is not None and current_ms < previous_ms:
                raise ValueError("센서 시간이 역순입니다.")
            if first_ms is None:
                first_ms = current_ms
            previous_ms = current_ms
    if first_ms is None or previous_ms <= first_ms:
        raise ValueError("센서 재생 시간이 없습니다.")
    return previous_ms - first_ms


def build_schedule(measurements, images_by_set):
    """서버에 존재하는 이미지와 DB 측정을 파일명으로 연결해 순서를 고정합니다."""
    records = {}
    for row in measurements:
        key = (row["set_number"], Path(row["image_name"]).stem.casefold())
        # 기존 프런트와 동일하게 확장자가 다른 JPG/PNG도 연결합니다.
        records.setdefault(key, row)

    items = []
    durations = {}
    for set_number, images in images_by_set.items():
        start_ms = 0
        position = 0
        for image in images:
            row = records.get((set_number, Path(image["name"]).stem.casefold()))
            if row is None:
                continue
            sensor_name = row["sensor_name"]
            duration_ms = PHOTO_DURATION_MS
            mode = "image_only"
            message = "센서 연결 없음 · 사진 2초 표시"
            if sensor_name:
                key = (set_number, sensor_name)
                if key not in durations:
                    try:
                        if Path(sensor_name).name != sensor_name or "\\" in sensor_name:
                            raise ValueError("허용되지 않는 센서 파일명입니다.")
                        path = get_image_path(f"sensors/set{set_number}/{sensor_name}")
                        durations[key] = (sensor_duration(path), "sensor", None)
                    except (OSError, ValueError, csv.Error):
                        durations[key] = (
                            PHOTO_DURATION_MS, "image_only",
                            "센서 파일 없음 또는 형식 오류 · 사진 2초 표시",
                        )
                duration_ms, mode, message = durations[key]
            items.append({
                "set_number": set_number,
                "position": position,
                "measurement_id": row["measurement_id"],
                "image_name": image["name"],
                "sensor_name": sensor_name,
                "start_ms": start_ms,
                "duration_ms": duration_ms,
                "playback_mode": mode,
                "message": message,
            })
            start_ms += duration_ms
            position += 1
    return items


def elapsed_ms(state, now):
    elapsed = state["elapsed_ms"]
    if state["status"] == "running":
        elapsed += max(0, int((now - state["resumed_at"]).total_seconds() * 1000))
    return elapsed


def state_response(state, items, now):
    elapsed = elapsed_ms(state, now)
    total_ms = max((item["start_ms"] + item["duration_ms"] for item in items), default=0)
    status = state["status"]
    cycle = elapsed // total_ms + 1 if total_ms else 0
    cycle_elapsed = elapsed % total_ms if total_ms else 0
    sets = []
    for set_number in range(4, 12):
        queue = [item for item in items if item["set_number"] == set_number]
        if not queue:
            sets.append({"set_number": set_number, "status": "empty", "total": 0})
            continue
        starts = [item["start_ms"] for item in queue]
        index = min(len(queue) - 1, max(0, bisect_right(starts, cycle_elapsed) - 1))
        item = queue[index]
        finished = cycle_elapsed >= queue[-1]["start_ms"] + queue[-1]["duration_ms"]
        sensor_url = None
        if item["playback_mode"] == "sensor":
            sensor_url = f"/api/sensors/set{set_number}/{quote(item['sensor_name'], safe='')}"
        sets.append({
            **item,
            "total": len(queue),
            "elapsed_ms": min(item["duration_ms"], max(0, cycle_elapsed - item["start_ms"])),
            "status": "completed" if finished else status,
            "image_url": f"/api/images/set{set_number}/{quote(item['image_name'], safe='')}",
            "sensor_url": sensor_url,
        })
    return {
        "server_time": now.replace(tzinfo=timezone.utc).isoformat(),
        "session_id": state["session_id"],
        "revision": state["revision"],
        "status": status,
        "elapsed_ms": elapsed,
        "cycle_number": cycle,
        "cycle_elapsed_ms": cycle_elapsed,
        "loop_enabled": True,
        "total_duration_ms": total_ms,
        "sets": sets,
    }
