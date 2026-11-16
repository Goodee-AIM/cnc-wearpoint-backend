import mimetypes
import re
from urllib.parse import quote

from botocore.exceptions import ClientError
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, StreamingResponse

from app.services.storage import (
    get_image_path,
    get_object_storage_object,
    list_object_names,
    using_object_storage,
)


router = APIRouter(
    prefix="/api/images",
    tags=["이미지 조회"],
)

IMAGE_NAME_PATTERN = re.compile(
    r"[A-Za-z0-9_.-]+\.(?:png|jpe?g)",
    re.IGNORECASE,
)


def validate_set(set_id: str) -> str:
    match = re.fullmatch(r"set(\d+)", set_id, re.IGNORECASE)

    if not match or not 4 <= int(match.group(1)) <= 11:
        raise HTTPException(
            status_code=400,
            detail="Set4~Set11만 사용할 수 있습니다.",
        )

    return f"set{int(match.group(1))}"


def natural_key(name: str):
    """파일명의 숫자를 고려하여 정렬합니다."""
    return [
        int(part) if part.isdigit() else part.lower()
        for part in re.split(r"(\d+)", name)
    ]


@router.get("/{set_id}")
def list_images(set_id: str):
    """선택한 Set의 이미지 목록을 반환합니다."""
    normalized_set = validate_set(set_id)

    prefix = f"images/{normalized_set}/original"

    try:
        names = list_object_names(prefix)
    except ClientError as exc:
        raise HTTPException(
            status_code=502,
            detail="Object Storage 이미지 목록 조회에 실패했습니다.",
        ) from exc

    items = []

    for name in names:
        if not IMAGE_NAME_PATTERN.fullmatch(name):
            continue

        items.append(
            {
                "name": name,
                "url": (
                    f"/api/images/{normalized_set}/"
                    f"{quote(name, safe='')}"
                ),
            }
        )

    items.sort(key=lambda item: natural_key(item["name"]))

    return {
        "set_name": f"Set{normalized_set[3:]}",
        "total": len(items),
        "items": items,
    }


@router.get("/{set_id}/{filename}")
def get_image(set_id: str, filename: str):
    """선택한 Set의 PNG 또는 JPG 이미지를 반환합니다."""
    normalized_set = validate_set(set_id)

    if not IMAGE_NAME_PATTERN.fullmatch(filename):
        raise HTTPException(
            status_code=400,
            detail="허용되지 않는 이미지 파일명입니다.",
        )

    object_key = (
        f"images/{normalized_set}/original/{filename}"
    )

    # 로컬 개발 환경
    if not using_object_storage():
        path = get_image_path(object_key)

        if not path.is_file():
            raise HTTPException(
                status_code=404,
                detail="이미지 파일을 찾을 수 없습니다.",
            )

        return FileResponse(path)

    # NHN Object Storage 운영 환경
    try:
        response = get_object_storage_object(object_key)
    except ClientError as exc:
        error_code = exc.response.get(
            "Error", {}
        ).get("Code", "")

        if error_code in {
            "404",
            "NoSuchKey",
            "NotFound",
        }:
            raise HTTPException(
                status_code=404,
                detail="이미지 파일을 찾을 수 없습니다.",
            ) from exc

        raise HTTPException(
            status_code=502,
            detail="Object Storage 이미지 조회에 실패했습니다.",
        ) from exc

    body = response["Body"]

    media_type = (
        mimetypes.guess_type(filename)[0]
        or response.get("ContentType")
        or "application/octet-stream"
    )

    headers = {}

    if response.get("ContentLength") is not None:
        headers["Content-Length"] = str(
            response["ContentLength"]
        )

    return StreamingResponse(
        body.iter_chunks(chunk_size=1024 * 1024),
        media_type=media_type,
        headers=headers,
    )