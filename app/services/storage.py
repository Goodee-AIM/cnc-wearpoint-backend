import os
from functools import lru_cache
from pathlib import Path, PurePosixPath

import boto3

from app.core.config import get_local_storage_root


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

            # 하위 디렉터리가 아니라 현재 prefix 바로 아래 파일만 반환
            if relative_name and "/" not in relative_name:
                names.append(relative_name)

    return names


def get_object_storage_object(object_key: str):
    """Object Storage에서 파일 객체를 가져옵니다."""
    key = normalize_object_key(object_key)

    return get_s3_client().get_object(
        Bucket=get_object_storage_bucket(),
        Key=key,
    )