import os
from pathlib import Path

from app.services.storage import (
    get_object_storage_bucket,
    get_s3_client,
    using_object_storage,
)


def save_uploaded_object(
    object_key: str,
    data: bytes,
    content_type: str,
) -> str:
    """
    업로드 파일을 현재 Storage Backend에 저장합니다.

    Object Storage 사용 시:
        S3-compatible Object Storage에 저장

    Local 사용 시:
        STORAGE_ROOT 아래에 저장
    """
    object_key = object_key.lstrip("/")

    if using_object_storage():
        client = get_s3_client()

        client.put_object(
            Bucket=get_object_storage_bucket(),
            Key=object_key,
            Body=data,
            ContentType=content_type,
        )

        return object_key

    storage_root = Path(
        os.getenv("STORAGE_ROOT", "./storage")
    ).resolve()

    target = (
        storage_root / object_key
    ).resolve()

    if (
        target != storage_root
        and storage_root not in target.parents
    ):
        raise ValueError(
            "허용되지 않은 Storage 경로입니다."
        )

    target.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    target.write_bytes(data)

    return object_key


def delete_uploaded_object(
    object_key: str,
) -> None:
    """
    DB 저장 실패 등의 경우 이미 저장한 파일을 정리합니다.
    """
    object_key = object_key.lstrip("/")

    if using_object_storage():
        client = get_s3_client()

        client.delete_object(
            Bucket=get_object_storage_bucket(),
            Key=object_key,
        )

        return

    storage_root = Path(
        os.getenv("STORAGE_ROOT", "./storage")
    ).resolve()

    target = (
        storage_root / object_key
    ).resolve()

    if (
        target != storage_root
        and storage_root not in target.parents
    ):
        return

    if target.is_file():
        target.unlink()