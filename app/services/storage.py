
import os
from functools import lru_cache
from pathlib import Path, PurePosixPath

import boto3
from botocore.exceptions import ClientError

from app.core.config import get_local_storage_root


IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg")


def get_storage_backend() -> str:
    """현재 파일 저장소 종류를 반환합니다."""
    backend = os.getenv("STORAGE_BACKEND", "local").strip().lower()

    if backend not in {"local", "s3"}:
        raise RuntimeError(
            f"Unsupported STORAGE_BACKEND: {backend}"
        )

    return backend


def using_object_storage() -> bool:
    """Object Storage 사용 여부를 반환합니다."""
    return get_storage_backend() == "s3"


def normalize_object_key(object_key: str) -> str:
    """Object Storage Key를 검증하고 정규화합니다."""
    normalized = object_key.replace("\\", "/")
    path = PurePosixPath(normalized)

    if not normalized or path.is_absolute() or ".." in path.parts:
        raise ValueError("Invalid object key")

    return path.as_posix()


def get_image_path(object_key: str) -> Path:
    """
    로컬 저장소 사용 시 논리적 Key를 실제 파일 경로로 변환합니다.

    기존 업로드 저장 경로 처리와의 호환성을 위해
    여기서는 파일 존재 여부를 검사하지 않습니다.
    """
    root = get_local_storage_root().resolve()
    key = normalize_object_key(object_key)
    path = (root / key).resolve()

    if not path.is_relative_to(root):
        raise ValueError("Invalid object key")

    return path


@lru_cache
def get_s3_client():
    """NHN Cloud Object Storage용 S3 client를 생성합니다."""
    endpoint = os.environ["OBJECT_STORAGE_ENDPOINT"]
    region = os.getenv("OBJECT_STORAGE_REGION", "KR1")

    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        region_name=region,
    )


def get_object_storage_bucket() -> str:
    """Object Storage 버킷 이름을 반환합니다."""
    return os.environ["OBJECT_STORAGE_BUCKET"]


def list_object_names(prefix: str) -> list[str]:
    """
    지정한 경로 바로 아래의 파일명 목록을 반환합니다.
    local / S3 저장소를 모두 지원합니다.
    """
    prefix = normalize_object_key(prefix)

    if not using_object_storage():
        folder = get_image_path(prefix)

        if not folder.is_dir():
            return []

        return [
            path.name
            for path in folder.iterdir()
            if path.is_file()
        ]

    client = get_s3_client()
    bucket = get_object_storage_bucket()

    s3_prefix = prefix.rstrip("/") + "/"
    names: list[str] = []

    paginator = client.get_paginator("list_objects_v2")

    for page in paginator.paginate(
        Bucket=bucket,
        Prefix=s3_prefix,
    ):
        for item in page.get("Contents", []):
            key = item["Key"]

            relative_name = key[len(s3_prefix):]

            # 하위 디렉터리는 제외
            if relative_name and "/" not in relative_name:
                names.append(relative_name)

    return names


def _is_image_key(object_key: str) -> bool:
    """
    이미지 경로인지 확인합니다.

    확장자 자동 탐색은 images/ 경로의 이미지에만 적용합니다.
    센서 CSV 등 다른 파일 유형은 영향을 받지 않습니다.
    """
    key = normalize_object_key(object_key)
    path = PurePosixPath(key)

    return (
        key.startswith("images/")
        and path.suffix.lower() in IMAGE_EXTENSIONS
    )


def _is_missing_object_error(exc: ClientError) -> bool:
    """S3 객체가 존재하지 않는 오류인지 판별합니다."""
    error = exc.response.get("Error", {})
    code = str(error.get("Code", ""))

    status = exc.response.get(
        "ResponseMetadata", {}
    ).get("HTTPStatusCode")

    return (
        code in {"NoSuchKey", "NotFound", "404"}
        or status == 404
    )


def _object_exists(object_key: str) -> bool:
    """
    실제 파일 존재 여부를 확인합니다.

    S3에서는 HEAD 요청을 사용하며 객체 내용을 다운로드하지 않습니다.
    권한 오류, 네트워크 오류 등은 누락으로 취급하지 않습니다.
    """
    key = normalize_object_key(object_key)

    if not using_object_storage():
        return get_image_path(key).is_file()

    try:
        get_s3_client().head_object(
            Bucket=get_object_storage_bucket(),
            Key=key,
        )
        return True

    except ClientError as exc:
        if _is_missing_object_error(exc):
            return False
        raise


def resolve_image_key(object_key: str) -> str:
    """
    실제 존재하는 이미지 Key를 반환합니다.

    처리 순서:
    1. 전달된 원본 Key 확인
    2. 존재하지 않을 때만 확장자 변경 탐색
    3. 하나만 발견되면 해당 Key 사용
    4. 여러 개 발견되면 모호성 오류
    5. 모두 없으면 FileNotFoundError

    DB 원본 파일명이나 Object Storage 객체를 변경하지 않습니다.
    """
    key = normalize_object_key(object_key)

    if not _is_image_key(key):
        raise ValueError("Invalid image object key")

    # 원본 경로 최우선
    if _object_exists(key):
        return key

    path = PurePosixPath(key)
    matches = []

    for extension in IMAGE_EXTENSIONS:
        candidate = path.with_suffix(extension).as_posix()

        if candidate == key:
            continue

        if _object_exists(candidate):
            matches.append(candidate)

    if len(matches) == 1:
        return matches[0]

    if len(matches) > 1:
        raise ValueError(
            "Ambiguous image extensions: "
            + ", ".join(matches)
        )

    raise FileNotFoundError(
        f"Image object not found: {key}"
    )


def get_object_storage_object(object_key: str):
    """
    Object Storage에서 파일 객체를 가져옵니다.

    이미지의 원본 Key가 없는 경우에만 동일한 파일명의
    .png / .jpg / .jpeg 확장자를 자동 탐색합니다.

    CSV 및 기타 파일은 기존의 정확한 Key 조회를 유지합니다.
    """
    key = normalize_object_key(object_key)

    client = get_s3_client()
    bucket = get_object_storage_bucket()

    try:
        # 원본 파일을 우선 사용
        return client.get_object(
            Bucket=bucket,
            Key=key,
        )

    except ClientError as exc:
        # 객체 누락 외의 오류는 그대로 전달
        if not _is_missing_object_error(exc):
            raise

        # 이미지가 아니면 확장자 탐색하지 않음
        if not _is_image_key(key):
            raise

        # 확장자만 다른 실제 객체 검색
        resolved_key = resolve_image_key(key)

        return client.get_object(
            Bucket=bucket,
            Key=resolved_key,
        )
