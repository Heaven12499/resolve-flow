package com.resolveflow.business.repository;

import com.resolveflow.business.domain.AiTask;
import org.springframework.data.jpa.repository.JpaRepository;
import java.util.Optional;
import java.util.Collection;
import java.util.List;
import com.resolveflow.business.domain.AiTaskStatus;

public interface AiTaskRepository extends JpaRepository<AiTask, Long> {
    Optional<AiTask> findByTaskId(String taskId);
    Optional<AiTask> findByIdempotencyKey(String idempotencyKey);
    List<AiTask> findByStatusIn(Collection<AiTaskStatus> statuses);
}
