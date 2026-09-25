package com.resolveflow.business.ai;

import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class AiTaskSignalListener {
    private final AiTaskWorker worker;

    public AiTaskSignalListener(AiTaskWorker worker) {
        this.worker = worker;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onTaskRequested(AiTaskRequested event) {
        worker.process(event.taskId());
    }
}
