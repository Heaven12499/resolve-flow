CREATE TABLE user_accounts (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    username VARCHAR(100) NOT NULL UNIQUE,
    password_hash VARCHAR(100) NOT NULL,
    role VARCHAR(20) NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
);

CREATE TABLE customers (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    name VARCHAR(100) NOT NULL,
    phone VARCHAR(30),
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
);

CREATE TABLE business_orders (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    order_no VARCHAR(64) NOT NULL UNIQUE,
    customer_id BIGINT NOT NULL,
    product_name VARCHAR(255) NOT NULL,
    amount DECIMAL(12,2) NOT NULL,
    status VARCHAR(30) NOT NULL,
    shipped_at DATETIME(6) NULL,
    promised_delivery_at DATETIME(6) NULL,
    version BIGINT NOT NULL DEFAULT 0,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    CONSTRAINT fk_orders_customer FOREIGN KEY (customer_id) REFERENCES customers(id),
    INDEX idx_orders_customer (customer_id)
);

CREATE TABLE logistics_events (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    order_id BIGINT NOT NULL,
    status VARCHAR(30) NOT NULL,
    description VARCHAR(500) NOT NULL,
    occurred_at DATETIME(6) NOT NULL,
    CONSTRAINT fk_logistics_order FOREIGN KEY (order_id) REFERENCES business_orders(id),
    INDEX idx_logistics_order_time (order_id, occurred_at)
);

CREATE TABLE tickets (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    ticket_no VARCHAR(64) NOT NULL UNIQUE,
    customer_id BIGINT NOT NULL,
    order_id BIGINT NOT NULL,
    title VARCHAR(255) NOT NULL,
    content LONGTEXT NOT NULL,
    intent VARCHAR(50),
    priority VARCHAR(20) NOT NULL DEFAULT 'medium',
    risk_level VARCHAR(20) NOT NULL DEFAULT 'unknown',
    status VARCHAR(30) NOT NULL,
    version BIGINT NOT NULL DEFAULT 0,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    CONSTRAINT fk_tickets_customer FOREIGN KEY (customer_id) REFERENCES customers(id),
    CONSTRAINT fk_tickets_order FOREIGN KEY (order_id) REFERENCES business_orders(id),
    INDEX idx_tickets_status_created (status, created_at),
    INDEX idx_tickets_order (order_id)
);

CREATE TABLE ticket_messages (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    ticket_id BIGINT NOT NULL,
    sender_type VARCHAR(20) NOT NULL,
    content LONGTEXT NOT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    CONSTRAINT fk_messages_ticket FOREIGN KEY (ticket_id) REFERENCES tickets(id),
    INDEX idx_messages_ticket_time (ticket_id, created_at)
);

CREATE TABLE approval_tasks (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    ticket_id BIGINT NOT NULL,
    task_type VARCHAR(50) NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'pending',
    proposed_data LONGTEXT NOT NULL,
    decision_data LONGTEXT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    decided_at DATETIME(6) NULL,
    CONSTRAINT fk_approvals_ticket FOREIGN KEY (ticket_id) REFERENCES tickets(id),
    INDEX idx_approvals_status (status, created_at)
);

CREATE TABLE ai_tasks (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    task_id VARCHAR(64) NOT NULL UNIQUE,
    ticket_id BIGINT NOT NULL,
    idempotency_key VARCHAR(120) NOT NULL,
    business_version BIGINT NOT NULL,
    status VARCHAR(20) NOT NULL,
    attempt_count INT NOT NULL DEFAULT 0,
    result_payload LONGTEXT NULL,
    error_code VARCHAR(100) NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    started_at DATETIME(6) NULL,
    finished_at DATETIME(6) NULL,
    CONSTRAINT uk_ai_task_idempotency UNIQUE (idempotency_key),
    CONSTRAINT fk_ai_tasks_ticket FOREIGN KEY (ticket_id) REFERENCES tickets(id),
    INDEX idx_ai_tasks_status_created (status, created_at)
);

CREATE TABLE audit_logs (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    ticket_id BIGINT NOT NULL,
    action VARCHAR(100) NOT NULL,
    operator_type VARCHAR(30) NOT NULL,
    details_json LONGTEXT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    CONSTRAINT fk_audit_ticket FOREIGN KEY (ticket_id) REFERENCES tickets(id),
    INDEX idx_audit_ticket_time (ticket_id, created_at)
);
