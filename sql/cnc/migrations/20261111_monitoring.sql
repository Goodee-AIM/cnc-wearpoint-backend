-- 기존 cnc_wearpoint DB에 공통 재생 상태 테이블만 추가합니다.
-- 저장 시각과 재생 기준 시각은 UTC입니다.
USE `cnc_wearpoint`;

CREATE TABLE IF NOT EXISTS `monitoring_state` (
    `id` tinyint unsigned NOT NULL,
    `session_id` char(36) DEFAULT NULL,
    `status` enum('idle','running','paused') NOT NULL DEFAULT 'idle',
    `elapsed_ms` bigint unsigned NOT NULL DEFAULT 0,
    `resumed_at` datetime(6) DEFAULT NULL,
    `revision` bigint unsigned NOT NULL DEFAULT 0,
    PRIMARY KEY (`id`),
    CONSTRAINT `chk_monitoring_singleton` CHECK (`id` = 1),
    CONSTRAINT `chk_monitoring_clock` CHECK (
        (`status` = 'running' AND `resumed_at` IS NOT NULL)
        OR (`status` <> 'running' AND `resumed_at` IS NULL)
    )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS `monitoring_items` (
    `set_number` int unsigned NOT NULL,
    `position` int unsigned NOT NULL,
    `measurement_id` bigint unsigned NOT NULL,
    `image_name` varchar(255) NOT NULL,
    `sensor_name` varchar(255) DEFAULT NULL,
    `start_ms` bigint unsigned NOT NULL,
    `duration_ms` bigint unsigned NOT NULL,
    `playback_mode` enum('sensor','image_only') NOT NULL,
    `message` varchar(255) DEFAULT NULL,
    PRIMARY KEY (`set_number`,`position`),
    CONSTRAINT `fk_monitoring_measurement` FOREIGN KEY (`measurement_id`)
        REFERENCES `measurements` (`id`),
    CONSTRAINT `chk_monitoring_duration` CHECK (`duration_ms` > 0),
    CONSTRAINT `chk_monitoring_set` CHECK (`set_number` BETWEEN 4 AND 11)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
