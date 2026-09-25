package com.resolveflow.business.repository;

import com.resolveflow.business.domain.ApprovalTask;
import org.springframework.data.jpa.repository.JpaRepository;
import java.util.List;

public interface ApprovalTaskRepository extends JpaRepository<ApprovalTask, Long> {
    List<ApprovalTask> findByTicketIdOrderByCreatedAtAsc(Long ticketId);
}
