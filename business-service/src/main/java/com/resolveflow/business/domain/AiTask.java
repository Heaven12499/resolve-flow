package com.resolveflow.business.domain;

import jakarta.persistence.*;
import java.time.Duration;
import java.time.Instant;

@Entity
@Table(name = "ai_tasks", uniqueConstraints = @UniqueConstraint(name = "uk_ai_task_idempotency", columnNames = "idempotency_key"))
public class AiTask {
    @Id @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;
    @Column(name = "task_id", nullable = false, unique = true, length = 64)
    private String taskId;
    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "ticket_id", nullable = false)
    private Ticket ticket;
    @Column(name = "idempotency_key", nullable = false, length = 120)
    private String idempotencyKey;
    @Column(name = "business_version", nullable = false)
    private long businessVersion;
    @Enumerated(EnumType.STRING) @Column(nullable = false, length = 20)
    private AiTaskStatus status = AiTaskStatus.PENDING;
    @Column(name = "attempt_count", nullable = false)
    private int attemptCount;
    @Lob @Column(name = "result_payload", columnDefinition = "LONGTEXT")
    private String resultPayload;
    @Column(name = "model_source", length = 50)
    private String modelSource;
    @Column(name = "error_code", length = 100)
    private String errorCode;
    @Column(name = "last_error", length = 500)
    private String lastError;
    @Column(name = "next_attempt_at", nullable = false)
    private Instant nextAttemptAt = Instant.now();
    @Column(name = "lease_expires_at")
    private Instant leaseExpiresAt;
    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt = Instant.now();
    @Column(name = "started_at")
    private Instant startedAt;
    @Column(name = "finished_at")
    private Instant finishedAt;

    protected AiTask() {}
    public AiTask(String taskId, Ticket ticket, String idempotencyKey, long businessVersion) {
        this.taskId = taskId; this.ticket = ticket; this.idempotencyKey = idempotencyKey;
        this.businessVersion = businessVersion;
    }
    public void start(Instant now, Duration leaseDuration) {
        if (status != AiTaskStatus.PENDING) throw new IllegalStateException("AI task is not pending");
        status = AiTaskStatus.RUNNING;
        attemptCount++;
        startedAt = now;
        finishedAt = null;
        errorCode = null;
        lastError = null;
        leaseExpiresAt = now.plus(leaseDuration);
    }
    public void recoverExpiredLease(Instant now, Instant retryAt) {
        if (status != AiTaskStatus.RUNNING || leaseExpiresAt == null || leaseExpiresAt.isAfter(now)) {
            throw new IllegalStateException("AI task lease is not expired");
        }
        status = AiTaskStatus.PENDING;
        errorCode = "EXECUTION_LEASE_EXPIRED";
        lastError = "Worker stopped before completing the leased attempt";
        nextAttemptAt = retryAt;
        startedAt = null;
        leaseExpiresAt = null;
    }
    public void scheduleRetry(String code, String detail, Instant retryAt) {
        status = AiTaskStatus.PENDING;
        errorCode = code;
        lastError = detail;
        nextAttemptAt = retryAt;
        startedAt = null;
        finishedAt = null;
        leaseExpiresAt = null;
    }
    public void succeed(String payload, String source) {
        status = AiTaskStatus.SUCCEEDED;
        resultPayload = payload;
        modelSource = source;
        errorCode = null;
        lastError = null;
        leaseExpiresAt = null;
        finishedAt = Instant.now();
    }
    public void fail(String code, String detail) {
        status = AiTaskStatus.FAILED;
        errorCode = code;
        lastError = detail;
        leaseExpiresAt = null;
        finishedAt = Instant.now();
    }
    public Long getId() { return id; }
    public String getTaskId() { return taskId; }
    public Ticket getTicket() { return ticket; }
    public long getBusinessVersion() { return businessVersion; }
    public AiTaskStatus getStatus() { return status; }
    public int getAttemptCount() { return attemptCount; }
    public String getErrorCode() { return errorCode; }
    public String getModelSource() { return modelSource; }
    public String getResultPayload() { return resultPayload; }
    public String getLastError() { return lastError; }
    public Instant getNextAttemptAt() { return nextAttemptAt; }
    public Instant getLeaseExpiresAt() { return leaseExpiresAt; }
    public Instant getCreatedAt() { return createdAt; }
    public Instant getStartedAt() { return startedAt; }
    public Instant getFinishedAt() { return finishedAt; }
}
