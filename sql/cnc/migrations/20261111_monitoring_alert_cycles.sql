-- 기존 공통 알림 이력을 1회차로 유지하고 반복 회차별 중복 방지 기준을 추가합니다.
-- 기존 DB에 한 번 적용합니다. 신규 DB는 갱신된 sql/cnc/schema.sql을 사용합니다.
ALTER TABLE `cnc_wearpoint`.`monitoring_alert_events`
    ADD COLUMN `cycle_number` bigint unsigned NOT NULL DEFAULT 1
        COMMENT '공통 재생 반복 회차(1부터 시작)' AFTER `session_id`,
    DROP INDEX `uq_monitoring_alert_occurrence`,
    ADD UNIQUE KEY `uq_monitoring_alert_occurrence`
        (`session_id`, `cycle_number`, `set_number`, `position`),
    ADD CONSTRAINT `chk_monitoring_alert_cycle` CHECK (`cycle_number` >= 1);
