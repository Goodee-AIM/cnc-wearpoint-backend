-- CNC WearPoint: separate replay-scoped inference runs from legacy predictions.
-- MySQL 8.4.x; apply ONCE after 20261111_monitoring.sql.
-- ADDITIVE only: no DROP, TRUNCATE, UPDATE of existing measurement/prediction/alert rows.
-- Application integration (generation increment, queue workers, HTTP status, UI)
-- MUST be deployed separately. This migration alone does NOT run inference.
SET NAMES utf8mb4;
USE `cnc_wearpoint`;

-- A restart within the same session begins cycle 1 again. This generation
-- distinguishes that restart from earlier cycle 1 in the same session.
-- Future /api/monitoring/restart must increment this under the state row lock.
-- /pause and /resume MUST NOT increment it.
ALTER TABLE `monitoring_state`
  ADD COLUMN `playback_generation` bigint unsigned NOT NULL DEFAULT 0
    COMMENT '동일 세션 재시작 구분값. restart 시 +1, pause/resume 때 유지'
    AFTER `revision`;

-- One row per replay occurrence, not one row per underlying measurement.
-- The same measurement can be inferred again in another cycle/restart.
-- completed results live here, not in the existing predictions table; the
-- legacy execute_prediction() prevents repeat writes for the same measurement.
CREATE TABLE IF NOT EXISTS `monitoring_inference_runs` (
  `id` bigint unsigned NOT NULL AUTO_INCREMENT,
  `run_id` char(36) NOT NULL COMMENT '각 추론 실행의 고유 ID(UUID)',
  `session_id` char(36) NOT NULL,
  `playback_generation` bigint unsigned NOT NULL COMMENT '재시작 구분값',
  `cycle_number` bigint unsigned NOT NULL COMMENT '반복 회차, 1부터 시작',
  `set_number` int unsigned NOT NULL COMMENT '4~11; 화면에는 Set1~8로 표시',
  `position` int unsigned NOT NULL COMMENT 'monitoring_items 내 재생 순번',
  `measurement_id` bigint unsigned NOT NULL COMMENT '해당 이미지+센서의 measurements.id',
  `image_name` varchar(255) NOT NULL COMMENT '대상 이미지명 스냅샷',
  `sensor_name` varchar(255) DEFAULT NULL COMMENT '대상 센서 파일명 스냅샷',
  `status` enum('queued','running','completed','failed','cancelled') NOT NULL DEFAULT 'queued',
  `attempt_count` int unsigned NOT NULL DEFAULT 0,
  `model_name` varchar(100) DEFAULT NULL,
  `model_version` varchar(100) DEFAULT NULL,
  `predicted_wear_um` decimal(12,5) DEFAULT NULL,
  `predicted_type` varchar(100) DEFAULT NULL,
  `wear_status` enum('normal','warning','danger') DEFAULT NULL,
  `error_code` varchar(64) DEFAULT NULL,
  `error_message` varchar(255) DEFAULT NULL COMMENT '비밀정보 없는 짧은 오류 설명',
  `queued_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  `started_at` datetime(6) DEFAULT NULL,
  `finished_at` datetime(6) DEFAULT NULL,
  `updated_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
    ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_monitoring_inference_run_id` (`run_id`),
  UNIQUE KEY `uq_monitoring_inference_occurrence`
    (`session_id`,`playback_generation`,`cycle_number`,`set_number`,`position`),
  KEY `idx_monitoring_inference_queue` (`status`,`queued_at`,`id`),
  KEY `idx_monitoring_inference_measurement` (`measurement_id`,`queued_at`),
  CONSTRAINT `fk_monitoring_inference_measurement`
    FOREIGN KEY (`measurement_id`) REFERENCES `measurements` (`id`),
  CONSTRAINT `chk_monitoring_inference_identity` CHECK (
    `cycle_number` >= 1 AND `set_number` BETWEEN 4 AND 11
  ),
  CONSTRAINT `chk_monitoring_inference_wear` CHECK (
    `predicted_wear_um` IS NULL OR `predicted_wear_um` >= 0
  ),
  CONSTRAINT `chk_monitoring_inference_completed` CHECK (
    (`status` = 'completed'
      AND `predicted_wear_um` IS NOT NULL
      AND `predicted_type` IS NOT NULL
      AND `wear_status` IS NOT NULL
      AND `model_name` IS NOT NULL
      AND `model_version` IS NOT NULL
      AND `finished_at` IS NOT NULL)
    OR (`status` <> 'completed'
      AND `predicted_wear_um` IS NULL
      AND `predicted_type` IS NULL
      AND `wear_status` IS NULL)
  )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='공통 재생의 세션/재시작/회차/Set/측정별 실제 AI 추론 대기·결과';
