-- 공통 재생 알림 이력을 추가합니다. 기존 alerts와 확인 이력은 유지합니다.
-- created_at은 재생 일정상의 발생 시각, recorded_at은 DB 기록 시각입니다. 둘 다 UTC입니다.
USE `cnc_wearpoint`;

CREATE TABLE IF NOT EXISTS `monitoring_alert_events` (
    `id` bigint unsigned NOT NULL AUTO_INCREMENT,
    `session_id` char(36) NOT NULL,
    `set_number` int unsigned NOT NULL,
    `position` int unsigned NOT NULL,
    `measurement_id` bigint unsigned NOT NULL,
    `prediction_id` bigint unsigned DEFAULT NULL,
    `image_name` varchar(255) NOT NULL,
    `sensor_name` varchar(255) DEFAULT NULL,
    `source` enum('label','prediction') NOT NULL,
    `level` enum('warning','danger') NOT NULL,
    `judged_wear_um` decimal(12,5) NOT NULL,
    `predicted_wear_um` decimal(12,5) DEFAULT NULL,
    `original_type` varchar(100) DEFAULT NULL,
    `warning_threshold_um` decimal(12,5) NOT NULL,
    `danger_threshold_um` decimal(12,5) NOT NULL,
    `message` varchar(255) NOT NULL,
    `created_at` datetime(6) NOT NULL,
    `recorded_at` datetime(6) NOT NULL,
    `detail_confirmed_at` datetime(6) DEFAULT NULL,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uq_monitoring_alert_occurrence` (`session_id`,`set_number`,`position`),
    KEY `idx_monitoring_alert_time` (`created_at`,`id`),
    CONSTRAINT `fk_monitoring_alert_measurement` FOREIGN KEY (`measurement_id`)
        REFERENCES `measurements` (`id`),
    CONSTRAINT `fk_monitoring_alert_prediction` FOREIGN KEY (`prediction_id`)
        REFERENCES `predictions` (`id`),
    CONSTRAINT `chk_monitoring_alert_wear` CHECK (`judged_wear_um` >= 0),
    CONSTRAINT `chk_monitoring_alert_thresholds` CHECK (
        `warning_threshold_um` >= 0 AND `danger_threshold_um` > `warning_threshold_um`
    ),
    CONSTRAINT `chk_monitoring_alert_confirmation` CHECK (
        `detail_confirmed_at` IS NULL OR `prediction_id` IS NOT NULL
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
