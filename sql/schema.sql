-- CNC WearPoint - baseline schema (2026-11-05)
-- Source: DBeaver MySQL 8.4.13 structure dump.
-- 신규 빈 데이터베이스를 구성할 때 사용하는 SQL입니다.
-- 기존 DB에 변경 내용을 반영하는 마이그레이션 SQL이 아닙니다.
-- DROP TABLE / 데이터 INSERT / LOCK TABLES 명령은 포함하지 않습니다.

SET NAMES utf8mb4;

CREATE DATABASE IF NOT EXISTS cnc_wearpoint
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_0900_ai_ci;

USE cnc_wearpoint;

-- 1. 공구 Set 정보와 가공 조건
CREATE TABLE IF NOT EXISTS tool_sets (
    id bigint unsigned NOT NULL AUTO_INCREMENT COMMENT '공구 Set 정보를 구분하는 내부 기본키(PK)',
    set_number int unsigned NOT NULL COMMENT 'MATWI 데이터셋의 공구 Set 번호',
    set_name varchar(50) NOT NULL COMMENT '공구 Set 이름(예: Set 5)',
    cutting_speed varchar(50) DEFAULT NULL COMMENT '절삭 속도(원본 sets.csv의 Vc)',
    spindle_speed varchar(50) DEFAULT NULL COMMENT '주축 회전 속도(원본 sets.csv의 n)',
    feed_per_tooth varchar(50) DEFAULT NULL COMMENT '날당 이송량(원본 sets.csv의 fz)',
    feed_rate varchar(50) DEFAULT NULL COMMENT '분당 이송 속도(원본 sets.csv의 Vf)',
    radial_depth varchar(50) DEFAULT NULL COMMENT '반경 방향 절삭 깊이(원본 sets.csv의 Ae)',
    axial_depth varchar(50) DEFAULT NULL COMMENT '축 방향 절삭 깊이(원본 sets.csv의 Ap)',
    material varchar(100) DEFAULT NULL COMMENT '가공 대상 소재명',
    crop_coordinates varchar(100) DEFAULT NULL COMMENT '이미지 전처리에 사용하는 원본 크롭 좌표',
    coating varchar(100) DEFAULT NULL COMMENT '공구의 코팅 정보',
    tooth_count int unsigned DEFAULT NULL COMMENT '공구의 절삭날 개수(원본 sets.csv의 z)',
    created_at datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '공구 Set 정보가 DB에 등록된 시각',
    PRIMARY KEY (id),
    UNIQUE KEY uq_tool_sets_number (set_number)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='MATWI 공구 Set별 가공 조건 및 이미지 전처리 기준 정보를 관리하는 테이블';

-- 2. 이미지·센서의 측정 메타데이터
CREATE TABLE IF NOT EXISTS measurements (
    id bigint unsigned NOT NULL AUTO_INCREMENT COMMENT '측정 기록을 구분하는 내부 기본키(PK)',
    set_id bigint unsigned NOT NULL COMMENT '측정 기록이 속한 공구 Set의 ID',
    measurement_key varchar(191) NOT NULL COMMENT '이미지와 센서 자료를 하나의 측정 기록으로 관리하기 위한 고유 식별값',
    image_name varchar(255) DEFAULT NULL COMMENT '원본 이미지 파일명',
    image_path text COMMENT '원본 이미지 파일의 상대경로',
    processed_image_path text COMMENT '전처리된 이미지 파일의 상대경로',
    sensor_name varchar(255) DEFAULT NULL COMMENT '원본 센서 파일명',
    sensor_path text COMMENT '원본 센서 파일의 상대경로(CSV 등)',
    processed_sensor_path text COMMENT '전처리된 센서 파일의 상대경로',
    source_image_id int unsigned DEFAULT NULL COMMENT 'MATWI labels.csv의 ImageID',
    source_sensor_id int unsigned DEFAULT NULL COMMENT 'MATWI labels.csv의 SensorID',
    image_captured_at datetime(6) DEFAULT NULL COMMENT '원본 이미지 촬영 시각',
    sensor_started_at datetime(6) DEFAULT NULL COMMENT '원본 센서 측정 시작 시각',
    sensor_ended_at datetime(6) DEFAULT NULL COMMENT '원본 센서 측정 종료 시각',
    status enum('waiting_input','ready','predicting','completed','failed') NOT NULL DEFAULT 'waiting_input' COMMENT '측정 자료의 처리 상태',
    error_message text COMMENT '측정 자료 처리 중 발생한 오류 메시지',
    created_at datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '측정 기록이 DB에 생성된 시각',
    updated_at datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6) COMMENT '측정 기록이 DB에서 마지막으로 수정된 시각',
    PRIMARY KEY (id),
    UNIQUE KEY uq_measurements_key (set_id,measurement_key),
    KEY idx_measurements_set_time (set_id,created_at),
    CONSTRAINT fk_measurements_set FOREIGN KEY (set_id) REFERENCES tool_sets (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='공구 Set별 이미지와 센서 데이터를 하나의 측정 기록으로 연결하고 원본 및 전처리 파일 정보를 관리하는 테이블';

-- 3. 원본 정답 라벨
CREATE TABLE IF NOT EXISTS wear_labels (
    id bigint unsigned NOT NULL AUTO_INCREMENT COMMENT '마모 정답 라벨을 구분하는 내부 기본키(PK)',
    measurement_id bigint unsigned NOT NULL COMMENT '정답 라벨이 속한 측정 기록의 ID(measurements.id)',
    actual_wear_um decimal(12,5) DEFAULT NULL COMMENT '전문가가 판정한 실제 마모량(원본 labels.csv의 wear, 단위 µm)',
    actual_type varchar(100) DEFAULT NULL COMMENT '실제 마모 유형(원본 labels.csv의 type)',
    created_at datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '마모 정답 라벨이 DB에 등록된 시각',
    PRIMARY KEY (id),
    UNIQUE KEY uq_wear_labels_measurement (measurement_id),
    CONSTRAINT fk_wear_labels_measurement FOREIGN KEY (measurement_id) REFERENCES measurements (id),
    CONSTRAINT chk_actual_wear CHECK ((actual_wear_um IS NULL) OR (actual_wear_um >= 0))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='측정 기록에 대응하는 전문가 판정 실제 마모량(µm)과 마모 유형을 관리하는 정답 라벨 테이블';

-- 4. AI 예측 결과와 당시 위험도 판정
CREATE TABLE IF NOT EXISTS predictions (
    id bigint unsigned NOT NULL AUTO_INCREMENT COMMENT 'AI 예측 결과를 구분하는 내부 기본키(PK)',
    measurement_id bigint unsigned NOT NULL COMMENT '예측 대상 측정 기록의 ID(measurements.id)',
    predicted_wear_um decimal(12,5) NOT NULL COMMENT 'AI 모델이 예측한 공구 마모량(단위 µm)',
    predicted_type varchar(100) DEFAULT NULL COMMENT 'AI 모델이 예측한 공구 마모 유형',
    model_name varchar(100) NOT NULL COMMENT '예측에 사용한 AI 모델의 이름(MLflow 등록 모델명)',
    model_version varchar(100) NOT NULL COMMENT '예측에 사용한 AI 모델의 버전(MLflow 등록 모델의 고정 버전 번호)',
    warning_threshold_um decimal(12,5) NOT NULL DEFAULT 50.00000 COMMENT '경고 상태 판정에 사용한 마모량 임계값(단위 µm)',
    danger_threshold_um decimal(12,5) NOT NULL DEFAULT 90.00000 COMMENT '위험 상태 판정에 사용한 마모량 임계값(단위 µm)',
    status enum('normal','warning','danger') NOT NULL COMMENT '예측 마모량과 임계값을 기준으로 판정한 상태(normal, warning, danger)',
    predicted_at datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT 'AI 모델의 예측 결과가 DB에 기록된 시각',
    PRIMARY KEY (id),
    KEY idx_predictions_measurement_time (measurement_id,predicted_at),
    CONSTRAINT fk_predictions_measurement FOREIGN KEY (measurement_id) REFERENCES measurements (id),
    CONSTRAINT chk_predicted_wear CHECK (predicted_wear_um >= 0),
    CONSTRAINT chk_prediction_status CHECK (
        (status = 'normal' AND predicted_wear_um < warning_threshold_um)
        OR (status = 'warning' AND predicted_wear_um >= warning_threshold_um AND predicted_wear_um < danger_threshold_um)
        OR (status = 'danger' AND predicted_wear_um >= danger_threshold_um)
    ),
    CONSTRAINT chk_prediction_thresholds CHECK (
        warning_threshold_um >= 0 AND danger_threshold_um > warning_threshold_um
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='측정 기록별 AI 모델 예측 결과와 사용 모델 정보 및 예측 당시 위험도 판정 이력을 관리하는 테이블';

-- 5. 공통 알림과 닫기 이력
CREATE TABLE IF NOT EXISTS alerts (
    id bigint unsigned NOT NULL AUTO_INCREMENT COMMENT '알림 기록을 구분하는 내부 기본키(PK)',
    prediction_id bigint unsigned NOT NULL COMMENT '알림 발생의 원인이 된 AI 예측 결과 ID(predictions.id)',
    level enum('warning','danger') NOT NULL COMMENT '알림의 위험 수준(warning, danger)',
    message varchar(255) NOT NULL COMMENT '사용자에게 표시할 경고 또는 위험 알림 메시지',
    acknowledged_at datetime(6) DEFAULT NULL COMMENT '상세 확인 시각(Null이면 미확인)',
    created_at datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '알림이 DB에 생성된 시각',
    PRIMARY KEY (id),
    UNIQUE KEY uq_alerts_prediction (prediction_id),
    CONSTRAINT fk_alerts_prediction FOREIGN KEY (prediction_id) REFERENCES predictions (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='AI 예측 결과에 따라 발생한 공통 경고·위험 알림과 알림 닫기 이력을 관리하는 테이블';

SHOW TABLES;

SELECT
    id,
    prediction_id,
    level,
    message,
      DATE_FORMAT(created_at, '%Y-%m-%d %H:%i:%s') AS created_at,
      DATE_FORMAT(detail_confirmed_at, '%Y-%m-%d %H:%i:%s') AS detail_confirmed_at
FROM cnc_wearpoint.alerts
ORDER BY id;

SELECT * FROM alerts ORDER BY id DESC;

DELETE FROM alerts WHERE id > 0;

