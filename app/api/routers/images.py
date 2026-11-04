import re
from urllib.parse import quote

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.services.storage import get_image_path


router = APIRouter(prefix="/api/images", tags=["이미지 조회"])

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
    """선택한 Set의 서버 이미지 목록을 반환합니다."""
    normalized_set = validate_set(set_id)
    folder = get_image_path(
        f"images/{normalized_set}/original"
    )

    if not folder.is_dir():
        return {
            "set_name": f"Set{normalized_set[3:]}",
            "total": 0,
            "items": [],
        }

    items = []

    for candidate in folder.iterdir():
        if not IMAGE_NAME_PATTERN.fullmatch(candidate.name):
            continue

        path = get_image_path(
            f"images/{normalized_set}/original/{candidate.name}"
        )

        if not path.is_file():
            continue

        items.append(
            {
                "name": candidate.name,
                "url": (
                    f"/api/images/{normalized_set}/"
                    f"{quote(candidate.name, safe='')}"
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
    """서버에 저장된 PNG 또는 JPG 이미지를 반환합니다."""
    normalized_set = validate_set(set_id)

    if not IMAGE_NAME_PATTERN.fullmatch(filename):
        raise HTTPException(
            status_code=400,
            detail="허용되지 않는 이미지 파일명입니다.",
        )

    path = get_image_path(
        f"images/{normalized_set}/original/{filename}"
    )

    if not path.is_file():
        raise HTTPException(
            status_code=404,
            detail="이미지 파일을 찾을 수 없습니다.",
        )

    return FileResponse(path)