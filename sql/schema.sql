CREATE DATABASE IF NOT EXISTS cnc_wearpoint
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE cnc_wearpoint;

-- 1. 공구 Set 정보와 가공 조건
CREATE TABLE IF NOT EXISTS tool_sets (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    set_number INT UNSIGNED NOT NULL,
    set_name VARCHAR(50) NOT NULL,

    cutting_speed VARCHAR(50) NULL COMMENT 'Vc 원본 값',
    spindle_speed VARCHAR(50) NULL COMMENT 'n 원본 값',
    feed_per_tooth VARCHAR(50) NULL COMMENT 'fz 원본 값',
    feed_rate VARCHAR(50) NULL COMMENT 'Vf 원본 값',
    radial_depth VARCHAR(50) NULL COMMENT 'Ae 원본 값',
    axial_depth VARCHAR(50) NULL COMMENT 'Ap 원본 값',
    material VARCHAR(100) NULL,
    crop_coordinates VARCHAR(100) NULL,
    coating VARCHAR(100) NULL,
    tooth_count INT UNSIGNED NULL COMMENT 'z',

    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),

    UNIQUE KEY uq_tool_sets_number (set_number)
);

-- 2. 이미지와 센서를 묶는 측정 정보
CREATE TABLE IF NOT EXISTS measurements (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    set_id BIGINT UNSIGNED NOT NULL,
    measurement_key VARCHAR(191) NOT NULL
        COMMENT '수집 프로그램에서 부여하는 공통 측정 식별값',

    image_name VARCHAR(255) NULL,
    image_path TEXT NULL,
    sensor_name VARCHAR(255) NULL,
    sensor_path TEXT NULL,

    source_image_id INT UNSIGNED NULL,
    source_sensor_id INT UNSIGNED NULL,

    image_captured_at DATETIME(6) NULL,
    sensor_started_at DATETIME(6) NULL,
    sensor_ended_at DATETIME(6) NULL,

    status ENUM(
        'waiting_input',
        'ready',
        'predicting',
        'completed',
        'failed'
    ) NOT NULL DEFAULT 'waiting_input',

    error_message TEXT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
        ON UPDATE CURRENT_TIMESTAMP(6),

    UNIQUE KEY uq_measurements_key (set_id, measurement_key),
    KEY idx_measurements_set_time (set_id, created_at),

    CONSTRAINT fk_measurements_set
        FOREIGN KEY (set_id) REFERENCES tool_sets(id)
);

-- 3. 데이터셋 정답 라벨
CREATE TABLE IF NOT EXISTS wear_labels (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    measurement_id BIGINT UNSIGNED NOT NULL,
    actual_wear_um DECIMAL(12, 5) NULL,
    actual_type VARCHAR(100) NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),

    UNIQUE KEY uq_wear_labels_measurement (measurement_id),

    CONSTRAINT fk_wear_labels_measurement
        FOREIGN KEY (measurement_id) REFERENCES measurements(id),

    CONSTRAINT chk_actual_wear
        CHECK (actual_wear_um IS NULL OR actual_wear_um >= 0)
);

-- 4. AI 예측 결과
CREATE TABLE IF NOT EXISTS predictions (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    measurement_id BIGINT UNSIGNED NOT NULL,

    predicted_wear_um DECIMAL(12, 5) NOT NULL,
    predicted_type VARCHAR(100) NULL,
    model_version VARCHAR(100) NOT NULL,

    warning_threshold_um DECIMAL(12, 5) NOT NULL DEFAULT 50,
    danger_threshold_um DECIMAL(12, 5) NOT NULL DEFAULT 90,
    status ENUM('normal', 'warning', 'danger') NOT NULL,

    predicted_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),

    KEY idx_predictions_measurement_time (
        measurement_id, predicted_at
    ),

    CONSTRAINT fk_predictions_measurement
        FOREIGN KEY (measurement_id) REFERENCES measurements(id),

    CONSTRAINT chk_predicted_wear
        CHECK (predicted_wear_um >= 0),

    CONSTRAINT chk_prediction_thresholds
        CHECK (
            warning_threshold_um >= 0
            AND danger_threshold_um > warning_threshold_um
        ),

    CONSTRAINT chk_prediction_status
        CHECK (
            (status = 'normal'
                AND predicted_wear_um < warning_threshold_um)
            OR
            (status = 'warning'
                AND predicted_wear_um >= warning_threshold_um
                AND predicted_wear_um < danger_threshold_um)
            OR
            (status = 'danger'
                AND predicted_wear_um >= danger_threshold_um)
        )
);

-- 5. 전체 Set 공통 알림
CREATE TABLE IF NOT EXISTS alerts (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    prediction_id BIGINT UNSIGNED NOT NULL,

    level ENUM('warning', 'danger') NOT NULL,
    message VARCHAR(255) NOT NULL,
    dismissed_at DATETIME(6) NULL
        COMMENT '알림의 닫기 버튼을 누른 시각',
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),

    UNIQUE KEY uq_alerts_prediction (prediction_id),
    KEY idx_alerts_dismissed_time (dismissed_at, created_at),

    CONSTRAINT fk_alerts_prediction
        FOREIGN KEY (prediction_id) REFERENCES predictions(id)
);

-- 생성된 테이블 확인
SHOW TABLES;