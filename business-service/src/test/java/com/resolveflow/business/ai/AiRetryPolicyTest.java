package com.resolveflow.business.ai;

import org.junit.jupiter.api.Test;
import java.time.Duration;
import static org.junit.jupiter.api.Assertions.*;

class AiRetryPolicyTest {
    private final AiRetryPolicy policy = new AiRetryPolicy(
            3, Duration.ofSeconds(2), Duration.ofSeconds(5));

    @Test
    void appliesCappedExponentialBackoff() {
        assertEquals(Duration.ofSeconds(2), policy.backoffFor(1));
        assertEquals(Duration.ofSeconds(4), policy.backoffFor(2));
        assertEquals(Duration.ofSeconds(5), policy.backoffFor(3));
        assertEquals(Duration.ofSeconds(5), policy.backoffFor(20));
    }

    @Test
    void retriesOnlyRetryableFailuresBeforeAttemptLimit() {
        assertTrue(policy.shouldRetry(1, true));
        assertTrue(policy.shouldRetry(2, true));
        assertFalse(policy.shouldRetry(3, true));
        assertFalse(policy.shouldRetry(1, false));
    }
}
