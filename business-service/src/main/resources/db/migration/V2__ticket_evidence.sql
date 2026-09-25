CREATE TABLE ticket_evidence (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    ticket_id BIGINT NOT NULL,
    order_id BIGINT NOT NULL,
    message_id BIGINT NOT NULL,
    file_name VARCHAR(255) NOT NULL,
    media_type VARCHAR(100) NOT NULL,
    storage_uri VARCHAR(500) NOT NULL,
    sha256 VARCHAR(64) NOT NULL,
    uploaded_by VARCHAR(30) NOT NULL DEFAULT 'customer',
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    CONSTRAINT uk_ticket_evidence_hash UNIQUE (ticket_id, sha256),
    CONSTRAINT fk_evidence_ticket FOREIGN KEY (ticket_id) REFERENCES tickets(id),
    CONSTRAINT fk_evidence_order FOREIGN KEY (order_id) REFERENCES business_orders(id),
    CONSTRAINT fk_evidence_message FOREIGN KEY (message_id) REFERENCES ticket_messages(id),
    INDEX idx_evidence_ticket_time (ticket_id, created_at)
);
