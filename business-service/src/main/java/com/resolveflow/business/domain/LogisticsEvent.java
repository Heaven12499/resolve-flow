package com.resolveflow.business.domain;

import jakarta.persistence.*;
import java.time.Instant;

@Entity
@Table(name = "logistics_events")
public class LogisticsEvent {
    @Id @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;
    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private BusinessOrder order;
    @Column(nullable = false, length = 30)
    private String status;
    @Column(nullable = false, length = 500)
    private String description;
    @Column(name = "occurred_at", nullable = false)
    private Instant occurredAt;

    protected LogisticsEvent() {}
    public LogisticsEvent(BusinessOrder order, String status, String description, Instant occurredAt) {
        this.order = order; this.status = status; this.description = description; this.occurredAt = occurredAt;
    }
    public Long getId() { return id; }
    public String getStatus() { return status; }
    public String getDescription() { return description; }
    public Instant getOccurredAt() { return occurredAt; }
}
