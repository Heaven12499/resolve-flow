package com.resolveflow.business.ai;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

@Component
public class AiTaskWorker {
    private static final Logger log = LoggerFactory.getLogger(AiTaskWorker.class);
    private final AiTaskPersistence persistence;
    private final AiTaskExecutor executor;
    private final AiFailureClassifier failureClassifier;
    public AiTaskWorker(AiTaskPersistence persistence, AiTaskExecutor executor,
                        AiFailureClassifier failureClassifier) {
        this.persistence = persistence; this.executor = executor; this.failureClassifier = failureClassifier;
    }

    public void process(String taskId) {
        try {
            var request = persistence.prepare(taskId);
            if (request.isEmpty()) return;
            executor.execute(taskId, request.get());
        } catch (Exception exception) {
            var failure = failureClassifier.classify(exception);
            log.warn("AI task {} dispatch failed: code={}, retryable={}",
                    taskId, failure.code(), failure.retryable(), exception);
            persistence.recordFailure(taskId, failure.code(), failure.detail(), failure.retryable());
        }
    }
}
