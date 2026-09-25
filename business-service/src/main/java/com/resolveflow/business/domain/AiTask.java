package com.resolveflow.business.domain;

import jakarta.persistence.*;
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
    @Lob @Column(name = "result_payload")
    private String resultPayload;
    @Column(name = "error_code", length = 100)
    private String errorCode;
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
    public void start() { status = AiTaskStatus.RUNNING; attemptCount++; startedAt = Instant.now(); }
    public void requeueAfterRestart() {
        status = AiTaskStatus.PENDING;
        errorCode = "RECOVERED_AFTER_RESTART";
        startedAt = null;
    }
    public void succeed(String payload) { status = AiTaskStatus.SUCCEEDED; resultPayload = payload; finishedAt = Instant.now(); }
    public void fail(String code) { status = AiTaskStatus.FAILED; errorCode = code; finishedAt = Instant.now(); }
    public Long getId() { return id; }
    public String getTaskId() { return taskId; }
    public Ticket getTicket() { return ticket; }
    public long getBusinessVersion() { return businessVersion; }
    public AiTaskStatus getStatus() { return status; }
}
