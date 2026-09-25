package com.resolveflow.business.ai;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class AiTaskWorker {
    private static final Logger log = LoggerFactory.getLogger(AiTaskWorker.class);
    private final AiTaskPersistence persistence;
    private final AiClient client;
    public AiTaskWorker(AiTaskPersistence persistence, AiClient client) {
        this.persistence = persistence; this.client = client;
    }

    @Async
    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void process(AiTaskRequested event) {
        try {
            var request = persistence.prepare(event.taskId());
            var result = client.analyze(request);
            persistence.apply(result);
        } catch (Exception exception) {
            log.error("AI task {} failed", event.taskId(), exception);
            persistence.fail(event.taskId(), exception.getClass().getSimpleName());
        }
    }
}
