-- Apply explicitly during a controlled migration BEFORE enabling the new Backend.
-- Do not reset existing predicting rows automatically: old attempts have no claim ID.
ALTER TABLE measurements
    ADD COLUMN prediction_claim_id CHAR(32) CHARACTER SET ascii COLLATE ascii_bin NULL
        COMMENT 'UUID of the active prediction attempt (fencing token)'
        AFTER status,
    ADD COLUMN prediction_started_at DATETIME(6) NULL
        COMMENT 'DB time when current prediction attempt was claimed'
        AFTER prediction_claim_id,
    ADD INDEX idx_measurements_claim_age (status, prediction_started_at);
