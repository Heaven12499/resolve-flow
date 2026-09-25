package com.resolveflow.business.ai;

import org.junit.jupiter.api.Test;
import org.springframework.web.client.ResourceAccessException;
import io.micrometer.core.instrument.Timer;
import java.util.Optional;
import static org.mockito.Mockito.*;

class AiTaskWorkerTest {
    @Test
    void duplicateSignalDoesNotInvokeAiWhenTaskCannotBeClaimed() {
        var persistence = mock(AiTaskPersistence.class);
        var executor = mock(AiTaskExecutor.class);
        when(persistence.prepare("AIT-1")).thenReturn(Optional.empty());
        var worker = new AiTaskWorker(persistence, executor, new AiFailureClassifier());

        worker.process("AIT-1");

        verifyNoInteractions(executor);
        verify(persistence, never()).recordFailure(any(), any(), any(), anyBoolean());
    }

    @Test
    void transientClientFailureIsRecordedAsRetryable() {
        var persistence = mock(AiTaskPersistence.class);
        var client = mock(AiClient.class);
        var request = mock(AiContracts.AnalyzeRequest.class);
        var metrics = mock(AiTaskMetrics.class);
        when(metrics.startAttempt()).thenReturn(mock(Timer.Sample.class));
        when(client.analyze(request)).thenThrow(new ResourceAccessException("timeout"));
        var executor = new AiTaskExecutor(persistence, client, new AiFailureClassifier(), metrics);

        executor.execute("AIT-2", request);

        verify(persistence).recordFailure(eq("AIT-2"), eq("AI_SERVICE_UNAVAILABLE"), eq("timeout"), eq(true));
    }
}
