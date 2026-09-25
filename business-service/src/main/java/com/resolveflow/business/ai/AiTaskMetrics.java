package com.resolveflow.business.ai;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.stereotype.Component;

@Component
public class AiTaskMetrics {
    private final MeterRegistry registry;
    private final Counter claimed;
    private final Counter retries;
    private final Counter escalations;
    private final Counter recoveredLeases;
    private final Timer duration;

    public AiTaskMetrics(MeterRegistry registry) {
        this.registry = registry;
        this.claimed = registry.counter("resolveflow.ai.tasks.claimed");
        this.retries = registry.counter("resolveflow.ai.tasks.retries");
        this.escalations = registry.counter("resolveflow.ai.tasks.escalations");
        this.recoveredLeases = registry.counter("resolveflow.ai.tasks.recovered.leases");
        this.duration = Timer.builder("resolveflow.ai.task.duration")
                .description("End-to-end duration of one AI task attempt")
                .publishPercentileHistogram()
                .register(registry);
    }

    public void claimed() { claimed.increment(); }
    public void retryScheduled() { retries.increment(); }
    public void escalated() { escalations.increment(); }
    public void leaseRecovered() { recoveredLeases.increment(); }
    public Timer.Sample startAttempt() { return Timer.start(registry); }
    public void finishAttempt(Timer.Sample sample, String outcome) {
        registry.counter("resolveflow.ai.task.attempts", "outcome", outcome).increment();
        sample.stop(duration);
    }
}
