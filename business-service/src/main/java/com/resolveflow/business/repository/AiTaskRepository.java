package com.resolveflow.business.repository;

import com.resolveflow.business.domain.AiTask;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.jpa.repository.EntityGraph;
import org.springframework.data.repository.query.Param;
import jakarta.persistence.LockModeType;
import java.time.Instant;
import java.util.Optional;
import java.util.List;
import com.resolveflow.business.domain.AiTaskStatus;

public interface AiTaskRepository extends JpaRepository<AiTask, Long> {
    Optional<AiTask> findByTaskId(String taskId);
    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select task from AiTask task where task.taskId = :taskId")
    Optional<AiTask> findByTaskIdForUpdate(@Param("taskId") String taskId);
    Optional<AiTask> findByIdempotencyKey(String idempotencyKey);
    @Query("select task.taskId from AiTask task where task.status = :status "
            + "and task.nextAttemptAt <= :now order by task.nextAttemptAt, task.createdAt")
    List<String> findDueTaskIds(@Param("status") AiTaskStatus status, @Param("now") Instant now,
                                org.springframework.data.domain.Pageable pageable);
    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select task from AiTask task where task.status = :status "
            + "and task.leaseExpiresAt <= :now order by task.leaseExpiresAt")
    List<AiTask> findExpiredLeasesForUpdate(@Param("status") AiTaskStatus status, @Param("now") Instant now,
                                            org.springframework.data.domain.Pageable pageable);
    @EntityGraph(attributePaths = "ticket")
    List<AiTask> findAllByOrderByCreatedAtDesc(org.springframework.data.domain.Pageable pageable);
}
