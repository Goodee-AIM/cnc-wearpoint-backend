import re

from botocore.exceptions import ClientError
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, StreamingResponse

from app.services.storage import (
    get_image_path,
    get_object_storage_object,
    using_object_storage,
)


router = APIRouter(
    prefix="/api/sensors",
    tags=["센서 조회"],
)

SENSOR_NAME_PATTERN = re.compile(
    r"[A-Za-z0-9_.-]+\.csv",
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


@router.get("/{set_id}/{filename}")
def get_sensor(set_id: str, filename: str):
    """선택한 Set의 센서 CSV 파일을 반환합니다."""
    normalized_set = validate_set(set_id)

    if not SENSOR_NAME_PATTERN.fullmatch(filename):
        raise HTTPException(
            status_code=400,
            detail="허용되지 않는 센서 파일명입니다.",
        )

    object_key = f"sensors/{normalized_set}/{filename}"

    # 로컬 개발 환경
    if not using_object_storage():
        try:
            path = get_image_path(object_key)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="허용되지 않는 센서 경로입니다.",
            ) from None

        if not path.is_file():
            raise HTTPException(
                status_code=404,
                detail="센서 CSV 파일을 찾을 수 없습니다.",
            )

        return FileResponse(
            path,
            media_type="text/csv",
        )

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
                detail="센서 CSV 파일을 찾을 수 없습니다.",
            ) from exc

        raise HTTPException(
            status_code=502,
            detail="Object Storage 센서 조회에 실패했습니다.",
        ) from exc

    body = response["Body"]

    headers = {}

    if response.get("ContentLength") is not None:
        headers["Content-Length"] = str(
            response["ContentLength"]
        )

    return StreamingResponse(
        body.iter_chunks(chunk_size=1024 * 1024),
        media_type="text/csv",
        headers=headers,
    )