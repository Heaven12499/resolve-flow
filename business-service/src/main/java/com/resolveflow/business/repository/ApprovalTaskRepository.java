package com.resolveflow.business.repository;

import com.resolveflow.business.domain.ApprovalTask;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import jakarta.persistence.LockModeType;
import java.util.List;
import java.util.Optional;

public interface ApprovalTaskRepository extends JpaRepository<ApprovalTask, Long> {
    List<ApprovalTask> findByTicketIdOrderByCreatedAtAsc(Long ticketId);
    List<ApprovalTask> findByStatusInOrderByCreatedAtAsc(List<String> statuses);
    boolean existsByTicketIdAndTaskTypeAndStatusIn(Long ticketId, String taskType, List<String> statuses);

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select task from ApprovalTask task where task.id = :id")
    Optional<ApprovalTask> findByIdForUpdate(@Param("id") Long id);
}
