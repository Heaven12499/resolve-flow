package com.resolveflow.business.domain;

import jakarta.persistence.*;
import java.time.Instant;

@Entity
@Table(name = "ticket_evidence", uniqueConstraints =
        @UniqueConstraint(name = "uk_ticket_evidence_hash", columnNames = {"ticket_id", "sha256"}))
public class TicketEvidence {
    @Id @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;
    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "ticket_id", nullable = false)
    private Ticket ticket;
    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "order_id", nullable = false)
    private BusinessOrder order;
    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "message_id", nullable = false)
    private TicketMessage message;
    @Column(name = "file_name", nullable = false, length = 255)
    private String fileName;
    @Column(name = "media_type", nullable = false, length = 100)
    private String mediaType;
    @Column(name = "storage_uri", nullable = false, length = 500)
    private String storageUri;
    @Column(nullable = false, length = 64)
    private String sha256;
    @Column(name = "uploaded_by", nullable = false, length = 30)
    private String uploadedBy = "customer";
    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt = Instant.now();

    protected TicketEvidence() {}
    public TicketEvidence(Ticket ticket, BusinessOrder order, TicketMessage message, String fileName,
                          String mediaType, String storageUri, String sha256) {
        this.ticket = ticket; this.order = order; this.message = message; this.fileName = fileName;
        this.mediaType = mediaType; this.storageUri = storageUri; this.sha256 = sha256.toLowerCase();
    }
    public Long getId() { return id; }
    public BusinessOrder getOrder() { return order; }
    public TicketMessage getMessage() { return message; }
    public String getFileName() { return fileName; }
    public String getMediaType() { return mediaType; }
    public String getStorageUri() { return storageUri; }
    public String getSha256() { return sha256; }
    public String getUploadedBy() { return uploadedBy; }
    public Instant getCreatedAt() { return createdAt; }
}
