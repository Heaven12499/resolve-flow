package com.resolveflow.business.domain;

import jakarta.persistence.*;
import java.time.Instant;

@Entity
@Table(name = "tickets")
public class Ticket {
    @Id @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;
    @Column(name = "ticket_no", nullable = false, unique = true, length = 64)
    private String ticketNo;
    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;
    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private BusinessOrder order;
    @Column(nullable = false, length = 255)
    private String title;
    @Lob @Column(nullable = false, columnDefinition = "LONGTEXT")
    private String content;
    @Column(length = 50)
    private String intent;
    @Column(nullable = false, length = 20)
    private String priority = "medium";
    @Column(name = "risk_level", nullable = false, length = 20)
    private String riskLevel = "unknown";
    @Column(name = "intake_idempotency_key", unique = true, length = 120)
    private String intakeIdempotencyKey;
    @Column(name = "intake_request_hash", length = 64)
    private String intakeRequestHash;
    @Enumerated(EnumType.STRING) @Column(nullable = false, length = 30)
    private TicketStatus status = TicketStatus.NEW;
    @Version
    private long version;
    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt = Instant.now();
    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt = Instant.now();

    protected Ticket() {}
    public Ticket(String ticketNo, Customer customer, BusinessOrder order, String title, String content) {
        this.ticketNo = ticketNo; this.customer = customer; this.order = order;
        this.title = title; this.content = content;
    }
    public void bindIntakeRequest(String idempotencyKey, String requestHash) {
        if (idempotencyKey == null) return;
        if (this.intakeIdempotencyKey != null) throw new IllegalStateException("工单接入幂等键已经绑定");
        this.intakeIdempotencyKey = idempotencyKey;
        this.intakeRequestHash = requestHash;
    }
    @PreUpdate void touch() { updatedAt = Instant.now(); }
    public void queueForAi() { transitionTo(TicketStatus.AI_QUEUED); }
    public void retryAi() { transitionTo(TicketStatus.AI_QUEUED); }
    public void applyAiResult(String intent, String priority, String riskLevel, TicketStatus nextStatus) {
        this.intent = intent; this.priority = priority; this.riskLevel = riskLevel; transitionTo(nextStatus);
    }
    public void failAi() { transitionTo(TicketStatus.AI_FAILED); }
    public void routeAiFailureToHumanReview() {
        transitionTo(TicketStatus.AI_FAILED);
        transitionTo(TicketStatus.HUMAN_REVIEW);
    }
    public void resolveFromHuman() { transitionTo(TicketStatus.RESOLVED); }
    public void waitForCustomer() { transitionTo(TicketStatus.WAITING_CUSTOMER); }
    private void transitionTo(TicketStatus next) {
        boolean allowed = switch (status) {
            case NEW -> next == TicketStatus.AI_QUEUED;
            case AI_QUEUED -> next == TicketStatus.RESOLVED || next == TicketStatus.PENDING_APPROVAL
                    || next == TicketStatus.HUMAN_REVIEW || next == TicketStatus.WAITING_CUSTOMER
                    || next == TicketStatus.AI_FAILED;
            case AI_FAILED -> next == TicketStatus.AI_QUEUED || next == TicketStatus.HUMAN_REVIEW;
            case WAITING_CUSTOMER -> next == TicketStatus.AI_QUEUED;
            case PENDING_APPROVAL -> next == TicketStatus.RESOLVED;
            case HUMAN_REVIEW -> next == TicketStatus.RESOLVED || next == TicketStatus.WAITING_CUSTOMER;
            default -> false;
        };
        if (!allowed) throw new IllegalStateException("Illegal ticket transition: " + status + " -> " + next);
        status = next;
    }
    public Long getId() { return id; }
    public String getTicketNo() { return ticketNo; }
    public Customer getCustomer() { return customer; }
    public BusinessOrder getOrder() { return order; }
    public String getTitle() { return title; }
    public String getContent() { return content; }
    public String getIntent() { return intent; }
    public String getPriority() { return priority; }
    public String getRiskLevel() { return riskLevel; }
    public String getIntakeIdempotencyKey() { return intakeIdempotencyKey; }
    public String getIntakeRequestHash() { return intakeRequestHash; }
    public TicketStatus getStatus() { return status; }
    public long getVersion() { return version; }
    public Instant getCreatedAt() { return createdAt; }
    public Instant getUpdatedAt() { return updatedAt; }
}
