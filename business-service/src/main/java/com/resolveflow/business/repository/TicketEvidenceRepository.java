package com.resolveflow.business.repository;

import com.resolveflow.business.domain.TicketEvidence;
import org.springframework.data.jpa.repository.JpaRepository;
import java.util.List;

public interface TicketEvidenceRepository extends JpaRepository<TicketEvidence, Long> {
    List<TicketEvidence> findByTicketIdOrderByCreatedAtAsc(Long ticketId);
    boolean existsByTicketIdAndSha256(Long ticketId, String sha256);
}
