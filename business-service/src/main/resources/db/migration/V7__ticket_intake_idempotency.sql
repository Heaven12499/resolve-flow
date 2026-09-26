ALTER TABLE tickets
    ADD COLUMN intake_idempotency_key VARCHAR(120) NULL,
    ADD COLUMN intake_request_hash VARCHAR(64) NULL,
    ADD CONSTRAINT uk_ticket_intake_idempotency UNIQUE (intake_idempotency_key);
