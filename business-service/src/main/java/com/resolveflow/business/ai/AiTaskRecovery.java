package com.resolveflow.business.ai;

import com.resolveflow.business.domain.AiTaskStatus;
import com.resolveflow.business.repository.AiTaskRepository;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;
import java.util.List;

@Component
public class AiTaskRecovery {
    private final AiTaskRepository tasks;
    private final ApplicationEventPublisher events;
    public AiTaskRecovery(AiTaskRepository tasks, ApplicationEventPublisher events) {
        this.tasks = tasks; this.events = events;
    }

    @EventListener(ApplicationReadyEvent.class)
    @Transactional
    public void recoverInterruptedTasks() {
        var interrupted = tasks.findByStatusIn(List.of(AiTaskStatus.PENDING, AiTaskStatus.RUNNING));
        for (var task : interrupted) {
            if (task.getStatus() == AiTaskStatus.RUNNING) task.requeueAfterRestart();
            events.publishEvent(new AiTaskRequested(task.getTaskId()));
        }
    }
}
