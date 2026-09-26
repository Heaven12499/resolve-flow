package com.resolveflow.business.repository;

import com.resolveflow.business.domain.BusinessActionExecution;
import org.springframework.data.jpa.repository.JpaRepository;
import java.util.List;
import java.util.Optional;

public interface BusinessActionExecutionRepository extends JpaRepository<BusinessActionExecution, Long> {
    Optional<BusinessActionExecution> findByIdempotencyKey(String idempotencyKey);
    List<BusinessActionExecution> findByTicketIdOrderByCreatedAtAsc(Long ticketId);
}
