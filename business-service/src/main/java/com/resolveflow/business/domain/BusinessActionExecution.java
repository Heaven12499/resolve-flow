package com.resolveflow.business.domain;

import jakarta.persistence.*;
import java.time.Instant;

@Entity
@Table(name = "business_action_executions")
public class BusinessActionExecution {
    @Id @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;
    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "ticket_id", nullable = false)
    private Ticket ticket;
    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "approval_task_id", nullable = false)
    private ApprovalTask approvalTask;
    @Column(name = "idempotency_key", nullable = false, unique = true, length = 120)
    private String idempotencyKey;
    @Column(name = "action_type", nullable = false, length = 50)
    private String actionType;
    @Column(nullable = false, length = 30)
    private String status;
    @Lob @Column(name = "request_json", nullable = false, columnDefinition = "LONGTEXT")
    private String requestJson;
    @Lob @Column(name = "result_json", columnDefinition = "LONGTEXT")
    private String resultJson;
    @Column(name = "external_reference", length = 120)
    private String externalReference;
    @Column(name = "error_message", length = 500)
    private String errorMessage;
    @Column(name = "attempt_count", nullable = false)
    private int attemptCount;
    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt = Instant.now();
    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt = Instant.now();

    protected BusinessActionExecution() {}

    public BusinessActionExecution(Ticket ticket, ApprovalTask approvalTask, String idempotencyKey,
                                   String actionType, String requestJson) {
        this.ticket = ticket;
        this.approvalTask = approvalTask;
        this.idempotencyKey = idempotencyKey;
        this.actionType = actionType;
        this.requestJson = requestJson;
        this.status = "pending";
    }

    public void succeed(String externalReference, String resultJson) {
        this.status = "succeeded";
        this.externalReference = externalReference;
        this.resultJson = resultJson;
        this.errorMessage = null;
        this.attemptCount++;
        this.updatedAt = Instant.now();
    }

    public void requireManualExecution(String resultJson) {
        this.status = "manual_required";
        this.resultJson = resultJson;
        this.attemptCount++;
        this.updatedAt = Instant.now();
    }

    public Long getId() { return id; }
    public String getIdempotencyKey() { return idempotencyKey; }
    public String getActionType() { return actionType; }
    public String getStatus() { return status; }
    public String getRequestJson() { return requestJson; }
    public String getResultJson() { return resultJson; }
    public String getExternalReference() { return externalReference; }
    public String getErrorMessage() { return errorMessage; }
    public int getAttemptCount() { return attemptCount; }
    public Instant getCreatedAt() { return createdAt; }
    public Instant getUpdatedAt() { return updatedAt; }
}
