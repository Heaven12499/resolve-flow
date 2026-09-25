package com.resolveflow.business.domain;

import jakarta.persistence.*;
import java.time.Instant;

@Entity
@Table(name = "audit_logs")
public class AuditLog {
    @Id @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;
    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "ticket_id", nullable = false)
    private Ticket ticket;
    @Column(nullable = false, length = 100)
    private String action;
    @Column(name = "operator_type", nullable = false, length = 30)
    private String operatorType;
    @Lob @Column(name = "details_json", columnDefinition = "LONGTEXT")
    private String detailsJson;
    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt = Instant.now();

    protected AuditLog() {}
    public AuditLog(Ticket ticket, String action, String operatorType, String detailsJson) {
        this.ticket = ticket; this.action = action; this.operatorType = operatorType; this.detailsJson = detailsJson;
    }
}
