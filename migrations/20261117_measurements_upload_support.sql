ALTER TABLE measurements
    MODIFY COLUMN set_id BIGINT UNSIGNED NULL,

    ADD COLUMN source_type
        ENUM('dataset', 'upload')
        NOT NULL
        DEFAULT 'dataset'
        COMMENT '데이터 출처: dataset=기존 데이터셋, upload=사용자 업로드'
        AFTER set_id,

    ADD COLUMN input_issue_reason
        VARCHAR(255)
        NULL
        COMMENT '이미지 또는 센서 입력 누락/미등록 사유'
        AFTER sensor_path;


UPDATE measurements
SET input_issue_reason =
    CASE
        WHEN (image_path IS NULL OR TRIM(image_path) = '')
         AND (sensor_path IS NULL OR TRIM(sensor_path) = '')
            THEN '이미지 및 센서 파일 미등록'

        WHEN image_path IS NULL OR TRIM(image_path) = ''
            THEN '이미지 파일 미등록'

        WHEN sensor_path IS NULL OR TRIM(sensor_path) = ''
            THEN '센서 파일 미등록'

        ELSE NULL
    END
WHERE source_type = 'dataset';


UPDATE measurements AS m
SET m.status =
    CASE
        WHEN m.image_path IS NULL
          OR TRIM(m.image_path) = ''
          OR m.sensor_path IS NULL
          OR TRIM(m.sensor_path) = ''
            THEN 'waiting_input'

        WHEN EXISTS (
            SELECT 1
            FROM predictions AS p
            WHERE p.measurement_id = m.id
        )
            THEN 'completed'

        ELSE 'ready'
    END
WHERE m.source_type = 'dataset';