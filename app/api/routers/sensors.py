import re

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.services.storage import get_image_path


router = APIRouter(
    prefix="/api/sensors",
    tags=["센서 조회"],
)

SENSOR_NAME_PATTERN = re.compile(
    r"[A-Za-z0-9_.-]+\.csv",
    re.IGNORECASE,
)


@router.get("/{set_id}/{filename}")
def get_sensor(set_id: str, filename: str):
    """선택한 Set의 센서 CSV를 반환합니다."""
    match = re.fullmatch(r"set(\d+)", set_id, re.IGNORECASE)

    if not match or not 4 <= int(match.group(1)) <= 11:
        raise HTTPException(
            status_code=400,
            detail="Set4~Set11만 사용할 수 있습니다.",
        )

    if not SENSOR_NAME_PATTERN.fullmatch(filename):
        raise HTTPException(
            status_code=400,
            detail="허용되지 않는 센서 파일명입니다.",
        )

    normalized_set = f"set{int(match.group(1))}"

    try:
        path = get_image_path(
            f"sensors/{normalized_set}/{filename}"
        )
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

    return FileResponse(path, media_type="text/csv")