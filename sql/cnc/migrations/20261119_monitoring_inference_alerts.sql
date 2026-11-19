-- Apply ONCE AFTER 20261119_monitoring_inference_runs.sql.
-- Adds identity for real-time inference alerts without rewriting historic data.
-- Existing historic rows get generation 0 and retain their original thresholds.
-- IMPORTANT: tested statically, not yet executed on MySQL.
SET NAMES utf8mb4;
USE `cnc_wearpoint`;

ALTER TABLE `monitoring_alert_events`
  ADD COLUMN `playback_generation` bigint unsigned NOT NULL DEFAULT 0
    COMMENT '재시작 구분값: 기존 이력은 0' AFTER `session_id`,
  ADD COLUMN `inference_run_id` char(36) DEFAULT NULL
    COMMENT '이번 회차 추론 UUID, legacy records remain NULL' AFTER `prediction_id`,
  DROP INDEX `uq_monitoring_alert_occurrence`,
  ADD UNIQUE KEY `uq_monitoring_alert_occurrence`
    (`session_id`, `playback_generation`, `cycle_number`, `set_number`, `position`),
  ADD KEY `idx_monitoring_alert_inference_run` (`inference_run_id`),
  DROP CHECK `chk_monitoring_alert_confirmation`,
  ADD CONSTRAINT `chk_monitoring_alert_confirmation` CHECK (
    `detail_confirmed_at` IS NULL
    OR `prediction_id` IS NOT NULL
    OR `inference_run_id` IS NOT NULL
  );
