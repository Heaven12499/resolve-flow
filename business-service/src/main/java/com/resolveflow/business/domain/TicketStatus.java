package com.resolveflow.business.domain;

public enum TicketStatus {
    NEW,
    AI_QUEUED,
    AI_PROCESSING,
    WAITING_CUSTOMER,
    PENDING_APPROVAL,
    HUMAN_REVIEW,
    RESOLVED,
    CLOSED,
    AI_FAILED
}
