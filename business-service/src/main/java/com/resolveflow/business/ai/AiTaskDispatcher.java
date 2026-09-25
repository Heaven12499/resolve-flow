package com.resolveflow.business.ai;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class AiTaskDispatcher {
    private static final Logger log = LoggerFactory.getLogger(AiTaskDispatcher.class);
    private final AiTaskPersistence persistence;
    private final AiTaskWorker worker;
    private final AiDispatchCoordinator coordinator;
    private final int batchSize;

    public AiTaskDispatcher(AiTaskPersistence persistence, AiTaskWorker worker,
                            AiDispatchCoordinator coordinator,
                            @Value("${resolveflow.ai.dispatch.batch-size:20}") int batchSize) {
        this.persistence = persistence; this.worker = worker; this.coordinator = coordinator;
        this.batchSize = batchSize;
    }

    @Scheduled(
            fixedDelayString = "${resolveflow.ai.dispatch.poll-interval:2s}",
            initialDelayString = "${resolveflow.ai.dispatch.initial-delay:2s}")
    public void dispatchDueTasks() {
        var lease = coordinator.tryAcquire();
        if (lease.isEmpty()) return;
        try (var ignored = lease.get()) {
            int recovered = persistence.recoverExpiredLeases(batchSize);
            var taskIds = persistence.findDueTaskIds(batchSize);
            taskIds.forEach(worker::process);
            if (recovered > 0 || !taskIds.isEmpty()) {
                log.info("AI dispatcher recovered {} leases and dispatched {} tasks", recovered, taskIds.size());
            }
        }
    }
}
