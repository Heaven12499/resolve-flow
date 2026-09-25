package com.resolveflow.business.ai;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import java.time.Duration;

@Component
public class AiRetryPolicy {
    private final int maxAttempts;
    private final Duration initialBackoff;
    private final Duration maxBackoff;

    public AiRetryPolicy(
            @Value("${resolveflow.ai.retry.max-attempts:3}") int maxAttempts,
            @Value("${resolveflow.ai.retry.initial-backoff:2s}") Duration initialBackoff,
            @Value("${resolveflow.ai.retry.max-backoff:30s}") Duration maxBackoff) {
        if (maxAttempts < 1) throw new IllegalArgumentException("maxAttempts must be positive");
        this.maxAttempts = maxAttempts;
        this.initialBackoff = initialBackoff;
        this.maxBackoff = maxBackoff;
    }

    public boolean shouldRetry(int completedAttempts, boolean retryable) {
        return retryable && completedAttempts < maxAttempts;
    }

    public Duration backoffFor(int completedAttempts) {
        int exponent = Math.max(0, Math.min(completedAttempts - 1, 30));
        long multiplier = 1L << exponent;
        try {
            Duration calculated = initialBackoff.multipliedBy(multiplier);
            return calculated.compareTo(maxBackoff) > 0 ? maxBackoff : calculated;
        } catch (ArithmeticException ignored) {
            return maxBackoff;
        }
    }
}
