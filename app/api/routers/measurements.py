import csv
import io
import logging
import math
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import (
    APIRouter,
    File,
    HTTPException,
    Path as ApiPath,
    UploadFile,
)

from PIL import Image

from app.core.database import get_connection
from app.services.upload_storage import (
    delete_uploaded_object,
    save_uploaded_object,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/measurements",
    tags=["measurements"],
)

MAX_IMAGE_SIZE = 8 * 1024 * 1024
MAX_SENSOR_SIZE = 20 * 1024 * 1024

# Serving(ml/serving/service.py)과 맞춘 입력 기준입니다.
FIXED_CROP = (1150, 670, 1750, 1070)
CROPPED_IMAGE_SIZE = (600, 400)
MAX_IMAGE_PIXELS = 50_000_000
# 모델 checkpoint의 window_size(512). 절삭 구간이 이보다 짧으면
# 추론 window를 만들 수 없으므로 파일 전체 행 수의 하한으로 사용합니다.
MIN_SENSOR_ROWS = 512


def detect_image_type(
    data: bytes,
) -> tuple[str, str]:
    """
    실제 파일 내용을 기준으로 이미지 형식을 확인합니다.

    반환:
        (확장자, Content-Type)
    """
    if data.startswith(
        b"\x89PNG\r\n\x1a\n"
    ):
        return ".png", "image/png"

    if data.startswith(
        b"\xff\xd8\xff"
    ):
        return ".jpg", "image/jpeg"

    raise HTTPException(
        status_code=422,
        detail=(
            "이미지는 PNG 또는 JPEG "
            "형식이어야 합니다."
        ),
    )


def validate_image_dimensions(
    data: bytes,
) -> tuple[int, int]:
    """
    Serving(ml/serving/service.py determine_crop)과 같은 기준으로
    이미지를 실제로 디코딩하고 크기를 확인합니다.

    - 600x400: 이미 ROI crop된 이미지
    - 그 외: FIXED_CROP(1150, 670, 1750, 1070)을 적용할 수 있어야 함
    """
    try:
        with Image.open(io.BytesIO(data)) as image:
            if image.format not in {"PNG", "JPEG"}:
                raise ValueError
            width, height = image.size
            if width * height > MAX_IMAGE_PIXELS:
                raise HTTPException(
                    status_code=422,
                    detail="이미지 해상도가 너무 큽니다.",
                )
            # 헤더만이 아니라 픽셀 데이터까지 읽어 손상 여부를 확인합니다.
            image.load()
    except HTTPException:
        raise
    except (OSError, ValueError, SyntaxError, Image.DecompressionBombError) as exc:
        raise HTTPException(
            status_code=422,
            detail="이미지 파일을 열 수 없습니다. 손상되었거나 지원하지 않는 형식입니다.",
        ) from exc

    if (width, height) == CROPPED_IMAGE_SIZE:
        return width, height

    _, _, crop_right, crop_bottom = FIXED_CROP
    if width < crop_right or height < crop_bottom:
        raise HTTPException(
            status_code=422,
            detail=(
                f"이미지 크기 {width}x{height}는 지원하지 않습니다. "
                f"{CROPPED_IMAGE_SIZE[0]}x{CROPPED_IMAGE_SIZE[1]} ROI 이미지이거나 "
                f"{crop_right}x{crop_bottom} 이상인 고정 카메라 원본이어야 합니다."
            ),
        )

    return width, height


def validate_sensor_csv(
    data: bytes,
) -> tuple[int, datetime, datetime]:
    """
    모델 입력 규격에 맞는 Sensor CSV인지 검사합니다.

    CSV 형식:
        acc
        audio
        force_x
        force_y
        force_z
        timestamp

    헤더 없이 총 6개 컬럼이어야 합니다.
    """
    try:
        text = data.decode("utf-8-sig")

        reader = csv.reader(
            io.StringIO(text),
            strict=True,
        )

        row_count = 0
        first_timestamp = None
        previous_timestamp = None
        last_timestamp = None
        expected_interval = None

        for cells in reader:
            if not cells:
                continue

            if all(
                not cell.strip()
                for cell in cells
            ):
                continue

            if len(cells) != 6:
                raise ValueError(
                    "Sensor CSV는 6개 컬럼이어야 합니다."
                )

            if any(
                not cell.strip()
                for cell in cells
            ):
                raise ValueError(
                    "Sensor CSV에 빈 값이 있습니다."
                )

            numeric_values = [
                float(value)
                for value in cells[:5]
            ]

            if not all(
                math.isfinite(value)
                for value in numeric_values
            ):
                raise ValueError(
                    "Sensor CSV에 유효하지 않은 "
                    "숫자가 있습니다."
                )

            timestamp_text = (
                cells[5]
                .strip()
                .replace(" ", "T")
            )

            current_timestamp = (
                datetime.fromisoformat(
                    timestamp_text
                )
            )

            if previous_timestamp is not None:
                try:
                    interval = (
                        current_timestamp
                        - previous_timestamp
                    )
                except TypeError:
                    raise ValueError(
                        "Sensor timestamp의 시간대 표기가 "
                        "행마다 다릅니다."
                    ) from None

                # Serving은 중복·역행 timestamp를 거절합니다.
                if interval.total_seconds() <= 0:
                    raise ValueError(
                        "Sensor timestamp가 중복되거나 "
                        "시간순으로 정렬되어 있지 않습니다."
                    )

                # Serving은 파일 내 샘플링 간격이 일정해야 합니다.
                if expected_interval is None:
                    expected_interval = interval
                elif interval != expected_interval:
                    raise ValueError(
                        "Sensor timestamp 간격이 일정하지 않습니다 "
                        f"({row_count + 1}번째 행)."
                    )

            if first_timestamp is None:
                first_timestamp = (
                    current_timestamp
                )

            previous_timestamp = (
                current_timestamp
            )

            last_timestamp = (
                current_timestamp
            )

            row_count += 1

        if (
            row_count < MIN_SENSOR_ROWS
            or first_timestamp is None
            or last_timestamp is None
        ):
            raise ValueError(
                f"Sensor CSV에는 최소 {MIN_SENSOR_ROWS}개 이상의 "
                f"데이터 행이 필요합니다 (현재 {row_count}행)."
            )

        return (
            row_count,
            first_timestamp,
            last_timestamp,
        )

    except (
        UnicodeError,
        ValueError,
        csv.Error,
        OverflowError,
    ) as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc)
            or (
                "Sensor CSV 형식이 "
                "올바르지 않습니다."
            ),
        ) from exc


def safe_filename(
    filename: str | None,
    fallback: str,
) -> str:
    if not filename:
        return fallback

    return Path(
        filename.replace("\\", "/")
    ).name[:255]


@router.post(
    "",
    status_code=201,
)
async def create_measurement(
    image: UploadFile = File(...),
    sensor_csv: UploadFile = File(...),
):
    """
    사용자 이미지와 Sensor CSV를 저장하고
    새로운 measurement를 생성합니다.
    """
    image_data = await image.read()
    sensor_data = await sensor_csv.read()

    if not image_data:
        raise HTTPException(
            status_code=422,
            detail="이미지 파일이 비어 있습니다.",
        )

    if not sensor_data:
        raise HTTPException(
            status_code=422,
            detail="Sensor CSV가 비어 있습니다.",
        )

    if len(image_data) > MAX_IMAGE_SIZE:
        raise HTTPException(
            status_code=413,
            detail="이미지는 8MB 이하만 가능합니다.",
        )

    if len(sensor_data) > MAX_SENSOR_SIZE:
        raise HTTPException(
            status_code=413,
            detail="Sensor CSV는 20MB 이하만 가능합니다.",
        )

    image_extension, image_content_type = (
        detect_image_type(
            image_data
        )
    )

    validate_image_dimensions(
        image_data
    )

    (
        row_count,
        sensor_started_at,
        sensor_ended_at,
    ) = validate_sensor_csv(
        sensor_data
    )

    measurement_key = (
        f"upload-{uuid.uuid4().hex}"
    )

    image_name = safe_filename(
        image.filename,
        f"image{image_extension}",
    )

    sensor_name = safe_filename(
        sensor_csv.filename,
        "sensor.csv",
    )

    image_object_key = (
        f"images/uploads/"
        f"{measurement_key}/"
        f"original{image_extension}"
    )

    sensor_object_key = (
        f"sensors/uploads/"
        f"{measurement_key}/"
        f"sensor.csv"
    )

    # 업로드된 객체 목록을 기록합니다.
    # DB 저장 전에 오류가 발생하면
    # 이미 저장된 객체를 정리하기 위해 사용합니다.
    saved_objects = []

    # DB commit 완료 여부를 기록합니다.
    # commit 이후에는 DB 데이터가 확정되므로
    # 업로드 파일을 삭제하지 않습니다.
    db_committed = False

    try:
        # 1. 이미지와 Sensor CSV를 먼저 저장합니다.
        # 둘 중 하나라도 실패하면
        # DB INSERT는 수행하지 않습니다.
        save_uploaded_object(
            image_object_key,
            image_data,
            image_content_type,
        )

        saved_objects.append(
            image_object_key
        )

        save_uploaded_object(
            sensor_object_key,
            sensor_data,
            "text/csv",
        )

        saved_objects.append(
            sensor_object_key
        )

        # 2. 파일 저장이 모두 성공한 경우에만
        # measurement를 DB에 생성합니다.
        connection = get_connection()

        try:
            cursor = connection.cursor(
                dictionary=True
            )

            try:
                cursor.execute(
                    """
                    INSERT INTO measurements (
                        set_id,
                        source_type,
                        measurement_key,
                        image_name,
                        image_path,
                        sensor_name,
                        sensor_path,
                        input_issue_reason,
                        sensor_started_at,
                        sensor_ended_at,
                        status
                    )
                    VALUES (
                        NULL,
                        'upload',
                        %s,
                        %s,
                        %s,
                        %s,
                        %s,
                        NULL,
                        %s,
                        %s,
                        'ready'
                    )
                    """,
                    (
                        measurement_key,
                        image_name,
                        image_object_key,
                        sensor_name,
                        sensor_object_key,
                        sensor_started_at,
                        sensor_ended_at,
                    ),
                )

                measurement_id = (
                    cursor.lastrowid
                )

                connection.commit()
                db_committed = True

            except Exception:
                # INSERT 또는 commit 과정에서 실패하면
                # 아직 commit되지 않은 DB 변경사항을
                # 되돌립니다.
                connection.rollback()
                raise

            finally:
                cursor.close()

        finally:
            connection.close()

    except Exception:
        # DB commit 전에 오류가 발생하면
        # 이미 저장된 이미지/센서 파일을 삭제하여
        # 저장 전 상태로 되돌립니다.
        if not db_committed:
            for object_key in reversed(
                saved_objects
            ):
                try:
                    delete_uploaded_object(
                        object_key
                    )
                except Exception as cleanup_error:
                    # 파일 정리 실패는 로그로 남기되,
                    # 최초 오류가 가려지지 않도록
                    # 다시 발생시키지는 않습니다.
                    logger.warning(
                        "업로드 파일 정리 실패 "
                        "(object_key=%s): %s",
                        object_key,
                        cleanup_error,
                    )

        # 최초에 발생한 오류를
        # 호출자에게 다시 전달합니다.
        raise

    return {
        "measurement_id": measurement_id,
        "measurement_key": measurement_key,
        "source_type": "upload",
        "set_id": None,
        "image_name": image_name,
        "image_path": image_object_key,
        "sensor_name": sensor_name,
        "sensor_path": sensor_object_key,
        "sensor_row_count": row_count,
        "sensor_started_at": (
            sensor_started_at.isoformat()
        ),
        "sensor_ended_at": (
            sensor_ended_at.isoformat()
        ),
        "status": "ready",
    }


@router.get("/{measurement_id}")
def get_measurement(
    measurement_id: int = ApiPath(
        ...,
        gt=0,
    ),
):
    """
    measurement 한 건을 조회합니다.
    """
    connection = get_connection()

    try:
        cursor = connection.cursor(
            dictionary=True
        )

        try:
            cursor.execute(
                """
                SELECT
                    id AS measurement_id,
                    set_id,
                    source_type,
                    measurement_key,
                    image_name,
                    image_path,
                    sensor_name,
                    sensor_path,
                    input_issue_reason,
                    image_captured_at,
                    sensor_started_at,
                    sensor_ended_at,
                    status,
                    created_at,
                    updated_at
                FROM measurements
                WHERE id = %s
                """,
                (measurement_id,),
            )

            measurement = (
                cursor.fetchone()
            )

            if measurement is None:
                raise HTTPException(
                    status_code=404,
                    detail=(
                        "Measurement를 "
                        "찾을 수 없습니다."
                    ),
                )

            return measurement

        finally:
            cursor.close()

    finally:
        connection.close()