"""기존 저장소의 센서 파일을 읽고 버전별 구간 계산 결과를 재사용합니다."""
from collections import OrderedDict
from threading import Lock

from app.services.cutting_segment import describe_cutting_segment
from app.services.storage import get_image_path, get_object_storage_object, using_object_storage

_cache = OrderedDict()
_lock = Lock()
_CAPACITY = 32
_MAX_BYTES = 32 * 1024 * 1024


def get_cutting_segment(object_key):
    body = None
    if using_object_storage():
        response = get_object_storage_object(object_key)
        body = response["Body"]
        version = response.get("VersionId") or response.get("ETag")
        cache_key = ("s3", object_key, version)
        size = response.get("ContentLength", 0)
    else:
        path = get_image_path(object_key)
        stat = path.stat()
        cache_key = ("local", str(path), stat.st_mtime_ns, stat.st_size)
        size = stat.st_size
    try:
        if size > _MAX_BYTES:
            raise ValueError("구간 계산은 32MiB 이하 센서 파일을 지원합니다.")
        with _lock:
            cached = _cache.get(cache_key)
            if cached is not None:
                _cache.move_to_end(cache_key)
                return dict(cached)
        if body is not None:
            data = body.read(_MAX_BYTES + 1)
        else:
            with path.open("rb") as source:
                data = source.read(_MAX_BYTES + 1)
        if len(data) > _MAX_BYTES:
            raise ValueError("구간 계산은 32MiB 이하 센서 파일을 지원합니다.")
        try:
            result = describe_cutting_segment(data)
        except ValueError as exc:
            result = {"status": "unavailable", "message": str(exc)}
        # 객체 버전을 모르면 오래된 결과를 재사용하지 않습니다.
        if body is None or version:
            with _lock:
                _cache[cache_key] = result
                _cache.move_to_end(cache_key)
                while len(_cache) > _CAPACITY:
                    _cache.popitem(last=False)
        return dict(result)
    finally:
        if body is not None:
            body.close()
