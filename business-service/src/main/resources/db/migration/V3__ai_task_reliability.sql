ALTER TABLE ai_tasks
    ADD COLUMN last_error VARCHAR(500) NULL AFTER error_code,
    ADD COLUMN next_attempt_at DATETIME(6) NULL AFTER last_error,
    ADD COLUMN lease_expires_at DATETIME(6) NULL AFTER next_attempt_at;

UPDATE ai_tasks
SET next_attempt_at = COALESCE(started_at, created_at)
WHERE next_attempt_at IS NULL;

UPDATE ai_tasks
SET lease_expires_at = CURRENT_TIMESTAMP(6)
WHERE status = 'RUNNING' AND lease_expires_at IS NULL;

ALTER TABLE ai_tasks
    MODIFY COLUMN next_attempt_at DATETIME(6) NOT NULL,
    ADD INDEX idx_ai_tasks_due (status, next_attempt_at),
    ADD INDEX idx_ai_tasks_lease (status, lease_expires_at);
