package com.resolveflow.business.domain;

import jakarta.persistence.*;
import java.time.Instant;

@Entity
@Table(name = "ticket_messages")
public class TicketMessage {
    @Id @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;
    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "ticket_id", nullable = false)
    private Ticket ticket;
    @Column(name = "sender_type", nullable = false, length = 20)
    private String senderType;
    @Lob @Column(nullable = false)
    private String content;
    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt = Instant.now();

    protected TicketMessage() {}
    public TicketMessage(Ticket ticket, String senderType, String content) {
        this.ticket = ticket; this.senderType = senderType; this.content = content;
    }
    public Long getId() { return id; }
    public String getSenderType() { return senderType; }
    public String getContent() { return content; }
    public Instant getCreatedAt() { return createdAt; }
}
