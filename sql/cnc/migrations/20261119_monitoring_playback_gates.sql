-- Opt-in per-Set playback gates. Requires monitoring_state.playback_generation
-- and monitoring_inference_runs (20261119_monitoring_inference_runs.sql).
-- The new table alone does not affect existing monitoring playback.
SET NAMES utf8mb4;
USE `cnc_wearpoint`;
CREATE TABLE IF NOT EXISTS `monitoring_playback_gates` (
  `set_number` int unsigned NOT NULL,
  `session_id` char(36) NOT NULL,
  `playback_generation` bigint unsigned NOT NULL,
  `cycle_number` bigint unsigned NOT NULL DEFAULT 1,
  `position` int unsigned NOT NULL,
  `measurement_id` bigint unsigned NOT NULL,
  `phase` enum('playing','waiting','showing') NOT NULL DEFAULT 'playing',
  `phase_elapsed_ms` bigint unsigned NOT NULL DEFAULT 0,
  `phase_started_at` datetime(6) DEFAULT NULL,
  `updated_at` datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
    ON UPDATE CURRENT_TIMESTAMP(6),
  PRIMARY KEY (`set_number`),
  KEY `idx_gate_occurrence` (`session_id`,`playback_generation`,`cycle_number`,`set_number`,`position`),
  CONSTRAINT `fk_gate_measurement` FOREIGN KEY (`measurement_id`)
    REFERENCES `measurements` (`id`),
  CONSTRAINT `chk_gate_set` CHECK (`set_number` BETWEEN 4 AND 11),
  CONSTRAINT `chk_gate_cycle` CHECK (`cycle_number` >= 1)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='공통 재생에서 Set별 센서 재생·AI 결과 대기·3초 표시 단계';
