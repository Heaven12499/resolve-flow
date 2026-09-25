package com.resolveflow.business.ai;

import com.resolveflow.business.repository.AiTaskRepository;
import org.springframework.data.domain.PageRequest;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.time.Instant;
import java.util.List;

@Service
public class AiTaskMonitor {
    private final AiTaskRepository tasks;

    public AiTaskMonitor(AiTaskRepository tasks) {
        this.tasks = tasks;
    }

    @Transactional(readOnly = true)
    public List<TaskView> latest(int limit) {
        return tasks.findAllByOrderByCreatedAtDesc(PageRequest.of(0, limit)).stream()
                .map(task -> new TaskView(
                        task.getTaskId(), task.getTicket().getId(), task.getTicket().getTicketNo(),
                        task.getStatus().name(), task.getAttemptCount(), task.getErrorCode(), task.getLastError(),
                        task.getNextAttemptAt(), task.getLeaseExpiresAt(), task.getCreatedAt(),
                        task.getStartedAt(), task.getFinishedAt()))
                .toList();
    }

    public record TaskView(
            String taskId,
            Long ticketId,
            String ticketNo,
            String status,
            int attemptCount,
            String errorCode,
            String lastError,
            Instant nextAttemptAt,
            Instant leaseExpiresAt,
            Instant createdAt,
            Instant startedAt,
            Instant finishedAt) {}
}
