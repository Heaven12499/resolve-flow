package com.resolveflow.business.domain;

import jakarta.persistence.*;
import java.time.Instant;

@Entity
@Table(name = "approval_tasks")
public class ApprovalTask {
    @Id @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;
    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "ticket_id", nullable = false)
    private Ticket ticket;
    @Column(name = "task_type", nullable = false, length = 50)
    private String taskType;
    @Column(nullable = false, length = 30)
    private String status = "pending";
    @Lob @Column(name = "proposed_data", nullable = false)
    private String proposedData;
    @Lob @Column(name = "decision_data")
    private String decisionData;
    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt = Instant.now();
    @Column(name = "decided_at")
    private Instant decidedAt;

    protected ApprovalTask() {}
    public ApprovalTask(Ticket ticket, String taskType, String proposedData) {
        this.ticket = ticket; this.taskType = taskType; this.proposedData = proposedData;
    }
    public void approve(String decisionData) { decide("approved", decisionData); }
    public void reject(String decisionData) { decide("rejected", decisionData); }
    public void assign(String decisionData) { decide("in_review", decisionData); }
    public void requestEvidence(String decisionData) { decide("in_review", decisionData); }
    private void decide(String nextStatus, String data) {
        if (!status.equals("pending") && !status.equals("in_review")) {
            throw new IllegalStateException("该审批任务已被处理");
        }
        status = nextStatus; decisionData = data; decidedAt = Instant.now();
    }
    public Long getId() { return id; }
    public String getTaskType() { return taskType; }
    public String getStatus() { return status; }
    public String getProposedData() { return proposedData; }
    public String getDecisionData() { return decisionData; }
    public Instant getCreatedAt() { return createdAt; }
    public Instant getDecidedAt() { return decidedAt; }
    public Ticket getTicket() { return ticket; }
}
