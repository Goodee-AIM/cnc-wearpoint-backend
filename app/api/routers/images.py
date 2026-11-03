import re

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.services.storage import get_image_path

router = APIRouter(prefix="/api/images", tags=["images"])


@router.get("/{set_id}/{filename}")
def get_image(set_id: str, filename: str):
    """
    Set과 파일명을 기준으로 로컬에 저장된 공구 이미지를 반환합니다.
    :param set_id: 이미지가 속한 데이터셋 식별자 (예: set7)
    :param filename: 조회할 이미지 파일명 (예: sample.jpg)
    :return: 이미지 파일 응답 (FileResponse)
    """

    # Set 형식 검증
    # set7, Set11 등 숫자가 포함된 Set 이름만 허용
    if not re.fullmatch(r"set[0-9]+", set_id, re.IGNORECASE):
        raise HTTPException(status_code=400, detail="Invalid set id")

    # 파일명 및 확장자 검증
    # ../ 등을 이용한 임의 경로 접근을 방지
    if not re.fullmatch(
            r"[A-Za-z0-9_.-]+\.(jpg)",
            filename,
            re.IGNORECASE,
    ):
        raise HTTPException(status_code=400, detail="Invalid filename")

    # 이미지의 논리적 경로(object_key) 생성
    # 로컬: storage/images/set7/original/sample.jpg
    # 만약 NHN Cloud 이전 시 동일한 object_key 사용 예쩡
    object_key = f"images/{set_id.lower()}/original/{filename}"

    # storage.py에서 저장소 경로를 조합하고 외부 경로 접근을 검증
    path = get_image_path(object_key)

    if not path.is_file():
        raise HTTPException(status_code=404, detail="Image not found")

    # 브라우저에서 이미지 직접 표시
    return FileResponse(path)