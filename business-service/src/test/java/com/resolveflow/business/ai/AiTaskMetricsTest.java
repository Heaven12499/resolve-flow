package com.resolveflow.business.ai;

import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class AiTaskMetricsTest {
    @Test
    void recordsLowCardinalityTaskOutcomes() {
        var registry = new SimpleMeterRegistry();
        var metrics = new AiTaskMetrics(registry);

        metrics.claimed();
        metrics.retryScheduled();
        var sample = metrics.startAttempt();
        metrics.finishAttempt(sample, "succeeded");

        assertEquals(1.0, registry.get("resolveflow.ai.tasks.claimed").counter().count());
        assertEquals(1.0, registry.get("resolveflow.ai.tasks.retries").counter().count());
        assertEquals(1.0, registry.get("resolveflow.ai.task.attempts")
                .tag("outcome", "succeeded").counter().count());
    }
}
