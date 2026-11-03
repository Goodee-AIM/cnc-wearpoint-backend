from pathlib import Path

from app.core.config import get_local_storage_root

def get_image_path(object_key: str) -> Path:
    """
    이미지의 논리적 경로를 로컬 파일 경로로 변환합니다.

    :param object_key: 이미지 저장 키 (예: images/set7/original/sample.jpg)
    :return: 검증된 로컬 이미지 경로
    """

    # 저장소 기준 경로를 절대 경로로 변환
    root = get_local_storage_root().resolve()

    # 전달받은 경로를 절대 경로로 변환
    path = (root / object_key).resolve()

    # 저장소 외부로 접근하는 경로 차단
    if not path.is_relative_to(root):
        raise ValueError("Invalid object key")

    return path