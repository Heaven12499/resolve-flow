package com.resolveflow.business.domain;

import org.junit.jupiter.api.Test;
import java.math.BigDecimal;
import java.time.Duration;
import java.time.Instant;
import static org.junit.jupiter.api.Assertions.*;

class AiTaskTest {
    private AiTask task() {
        var customer = new Customer("test", null);
        var order = new BusinessOrder("O-1", customer, "product", BigDecimal.ONE,
                "shipped", Instant.now(), Instant.now());
        var ticket = new Ticket("T-1", customer, order, "title", "content");
        ticket.queueForAi();
        return new AiTask("AIT-1", ticket, "ticket:1:version:1", ticket.getVersion());
    }

    @Test
    void executionLeaseAndRetryPreserveAttemptCount() {
        var task = task();
        Instant firstStart = Instant.parse("2026-09-25T00:00:00Z");
        task.start(firstStart, Duration.ofSeconds(45));

        assertEquals(AiTaskStatus.RUNNING, task.getStatus());
        assertEquals(1, task.getAttemptCount());
        assertEquals(firstStart.plusSeconds(45), task.getLeaseExpiresAt());

        Instant retryAt = firstStart.plusSeconds(2);
        task.scheduleRetry("AI_SERVICE_UNAVAILABLE", "connection refused", retryAt);
        assertEquals(AiTaskStatus.PENDING, task.getStatus());
        assertEquals(retryAt, task.getNextAttemptAt());

        task.start(retryAt, Duration.ofSeconds(45));
        assertEquals(2, task.getAttemptCount());
        assertNull(task.getErrorCode());
    }

    @Test
    void expiredLeaseCanBeRecoveredButActiveLeaseCannot() {
        var task = task();
        Instant start = Instant.parse("2026-09-25T00:00:00Z");
        task.start(start, Duration.ofSeconds(30));

        assertThrows(IllegalStateException.class,
                () -> task.recoverExpiredLease(start.plusSeconds(29), start.plusSeconds(31)));

        Instant retryAt = start.plusSeconds(35);
        task.recoverExpiredLease(start.plusSeconds(31), retryAt);
        assertEquals(AiTaskStatus.PENDING, task.getStatus());
        assertEquals("EXECUTION_LEASE_EXPIRED", task.getErrorCode());
        assertEquals(retryAt, task.getNextAttemptAt());
        assertNull(task.getLeaseExpiresAt());
    }

    @Test
    void successfulResultKeepsItsDecisionSource() {
        var task = task();
        task.start(Instant.parse("2026-09-25T00:00:00Z"), Duration.ofSeconds(30));

        task.succeed("{\"model_source\":\"rules\"}", "rules");

        assertEquals(AiTaskStatus.SUCCEEDED, task.getStatus());
        assertEquals("rules", task.getModelSource());
    }
}
