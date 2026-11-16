"""Independent upload store; never writes monitoring, measurements or alerts."""
import base64
import binascii
import csv
import io
import json
import math
import os
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from starlette.concurrency import run_in_threadpool

router = APIRouter(prefix="/api/manual-inputs", tags=["manual-inputs"])
MAX_BODY = 40 * 1024 * 1024


def root():
    # Dedicated writable volume, separate from the read-only MATWI data volume.
    path = Path(os.getenv("MANUAL_INPUT_ROOT", "./manual-inputs")).resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def entry_path(identifier):
    if not re.fullmatch(r"[a-f0-9]{32}", identifier):
        raise HTTPException(404, "입력 기록을 찾을 수 없습니다.")
    path = root() / identifier
    if not (path / "metadata.json").is_file():
        raise HTTPException(404, "입력 기록을 찾을 수 없습니다.")
    return path


def validate_csv(data):
    try:
        text = data.decode("utf-8-sig")
        previous = None
        first = None
        count = 0
        for cells in csv.reader(io.StringIO(text), strict=True):
            if not cells or all(not c.strip() for c in cells):
                continue
            count += 1
            if len(cells) != 6 or any(not c.strip() for c in cells):
                raise ValueError()
            if not all(math.isfinite(float(c)) for c in cells[:5]):
                raise ValueError()
            stamp = cells[5].strip().replace(" ", "T")
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,9})?", stamp):
                raise ValueError()
            current = datetime.fromisoformat(stamp[:26])
            if previous is not None and current < previous:
                raise ValueError()
            first = current if first is None else first
            previous = current
        if count < 2 or previous <= first:
            raise ValueError()
        return count, round((previous - first).total_seconds() * 1000)
    except (UnicodeError, ValueError, csv.Error, OverflowError):
        raise HTTPException(422, "센서 CSV는 헤더 없는 숫자 5열·시간 1열이며, 시간순으로 정렬된 두 행 이상이어야 합니다.")


def save(payload):
    try:
        image = base64.b64decode(payload["image_base64"], validate=True)
        sensor = base64.b64decode(payload["sensor_base64"], validate=True)
        image_name = str(payload["image_name"])
        sensor_name = str(payload["sensor_name"])
    except (KeyError, TypeError, ValueError, binascii.Error):
        raise HTTPException(422, "이미지와 CSV를 모두 선택하세요.")
    if len(image) > 8 * 1024 * 1024 or len(sensor) > 20 * 1024 * 1024:
        raise HTTPException(413, "이미지는 8MB, CSV는 20MB 이하로 선택하세요.")
    if image.startswith(b"\x89PNG\r\n\x1a\n"):
        extension = "png"
    elif image.startswith(b"\xff\xd8\xff"):
        extension = "jpg"
    elif image[:4] == b"RIFF" and image[8:12] == b"WEBP":
        extension = "webp"
    else:
        raise HTTPException(422, "PNG·JPEG·WebP 이미지를 선택하세요.")
    count, duration = validate_csv(sensor)
    store = root()
    # Bound storage until explicit retention management is added.
    if sum(p.stat().st_size for p in store.glob("*/*") if p.is_file()) + len(image) + len(sensor) > int(os.getenv("MANUAL_INPUT_QUOTA_MB", "512")) * 1024 * 1024:
        raise HTTPException(507, "사용자 입력 저장 공간이 부족합니다. 관리자에게 문의하세요.")
    identifier = uuid.uuid4().hex
    staging = store / (".tmp-" + identifier)
    staging.mkdir()
    metadata = {
        "id": identifier, "image_name": Path(image_name.replace("\\", "/")).name[:255],
        "sensor_name": Path(sensor_name.replace("\\", "/")).name[:255],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "image_url": f"/api/manual-inputs/{identifier}/image",
        "sensor_url": f"/api/manual-inputs/{identifier}/sensor",
        "image_file": f"image.{extension}", "row_count": count, "duration_ms": max(1, duration),
        "prediction_status": "pending", "predicted_wear": None, "wear_type": None,
    }
    try:
        (staging / metadata["image_file"]).write_bytes(image)
        (staging / "sensor.csv").write_bytes(sensor)
        (staging / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False), encoding="utf-8")
        staging.rename(store / identifier)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return metadata


@router.post("", status_code=201)
async def upload(request: Request):
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > MAX_BODY:
            raise HTTPException(413, "업로드 크기가 너무 큽니다.")
    try:
        payload = json.loads(data)
        if not isinstance(payload, dict):
            raise ValueError()
    except (ValueError, UnicodeError):
        raise HTTPException(422, "잘못된 업로드 요청입니다.")
    return await run_in_threadpool(save, payload)


@router.get("")
def list_inputs():
    items = [json.loads(p.read_text(encoding="utf-8")) for p in root().glob("*/metadata.json") if not p.parent.name.startswith(".")]
    return {"items": sorted(items, key=lambda item: item["created_at"], reverse=True)}


# Playlists reference existing UUID records; they never alter shared monitoring.
def playlist_dir():
    folder = root() / ".playlists"
    folder.mkdir(exist_ok=True)
    return folder


def expand_playlist(data):
    return {**data, "items": [get_input(identifier) for identifier in data["item_ids"]]}


@router.get("/playlists")
def list_playlists():
    items = [expand_playlist(json.loads(p.read_text(encoding="utf-8"))) for p in playlist_dir().glob("*.json")]
    return {"items": sorted(items, key=lambda item: item["created_at"], reverse=True)}


@router.post("/playlists", status_code=201)
async def create_playlist(request: Request):
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > 65536:
            raise HTTPException(413, "재생 목록 요청이 너무 큽니다.")
    try:
        payload = json.loads(body)
        ids = payload["item_ids"]
        if not isinstance(ids, list) or not 1 <= len(ids) <= 1000 or not all(isinstance(item, str) for item in ids) or len(set(ids)) != len(ids):
            raise ValueError()
        name = str(payload.get("name") or "Set test")[:200]
    except (ValueError, KeyError, TypeError, UnicodeError):
        raise HTTPException(422, "유효한 입력 ID 목록이 필요합니다.")
    # Validate all referenced records before publishing the ordered list.
    for identifier in ids:
        entry_path(identifier)
    data = {"id": uuid.uuid4().hex, "name": name, "item_ids": ids,
            "created_at": datetime.now(timezone.utc).isoformat()}
    folder = playlist_dir()
    temporary = folder / (data["id"] + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    temporary.rename(folder / (data["id"] + ".json"))
    return expand_playlist(data)


@router.get("/{identifier}")
def get_input(identifier: str):
    return json.loads((entry_path(identifier) / "metadata.json").read_text(encoding="utf-8"))


@router.get("/{identifier}/image")
def get_image(identifier: str):
    path = entry_path(identifier)
    metadata = json.loads((path / "metadata.json").read_text(encoding="utf-8"))
    return FileResponse(path / metadata["image_file"])


@router.get("/{identifier}/sensor")
def get_sensor(identifier: str):
    return FileResponse(entry_path(identifier) / "sensor.csv", media_type="text/csv")
