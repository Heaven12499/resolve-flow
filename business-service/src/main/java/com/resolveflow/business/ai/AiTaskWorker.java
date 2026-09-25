package com.resolveflow.business.ai;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.slf4j.MDC;
import com.resolveflow.business.web.RequestIdFilter;
import java.util.UUID;

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
        boolean generatedRequestId = MDC.get(RequestIdFilter.MDC_KEY) == null;
        if (generatedRequestId) MDC.put(RequestIdFilter.MDC_KEY, UUID.randomUUID().toString());
        try {
            var request = persistence.prepare(taskId);
            if (request.isEmpty()) return;
            executor.execute(taskId, request.get());
        } catch (Exception exception) {
            var failure = failureClassifier.classify(exception);
            log.warn("AI task {} dispatch failed: code={}, retryable={}",
                    taskId, failure.code(), failure.retryable(), exception);
            persistence.recordFailure(taskId, failure.code(), failure.detail(), failure.retryable());
        } finally {
            if (generatedRequestId) MDC.remove(RequestIdFilter.MDC_KEY);
        }
    }
}
