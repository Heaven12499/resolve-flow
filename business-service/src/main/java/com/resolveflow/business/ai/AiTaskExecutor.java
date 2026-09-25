package com.resolveflow.business.ai;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Component;

@Component
public class AiTaskExecutor {
    private static final Logger log = LoggerFactory.getLogger(AiTaskExecutor.class);
    private final AiTaskPersistence persistence;
    private final AiClient client;
    private final AiFailureClassifier failureClassifier;

    public AiTaskExecutor(AiTaskPersistence persistence, AiClient client,
                          AiFailureClassifier failureClassifier) {
        this.persistence = persistence; this.client = client; this.failureClassifier = failureClassifier;
    }

    @Async("applicationTaskExecutor")
    public void execute(String taskId, AiContracts.AnalyzeRequest request) {
        try {
            var result = client.analyze(request);
            persistence.apply(result);
        } catch (Exception exception) {
            var failure = failureClassifier.classify(exception);
            log.warn("AI task {} attempt failed: code={}, retryable={}",
                    taskId, failure.code(), failure.retryable(), exception);
            persistence.recordFailure(taskId, failure.code(), failure.detail(), failure.retryable());
        }
    }
}
