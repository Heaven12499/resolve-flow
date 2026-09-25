package com.resolveflow.business.ai;

import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.HttpServerErrorException;
import org.springframework.web.client.ResourceAccessException;
import static org.junit.jupiter.api.Assertions.*;

class AiFailureClassifierTest {
    private final AiFailureClassifier classifier = new AiFailureClassifier();

    @Test
    void networkRateLimitAndServerFailuresAreRetryable() {
        assertTrue(classifier.classify(new ResourceAccessException("timeout")).retryable());
        assertTrue(classifier.classify(new HttpClientErrorException(HttpStatus.TOO_MANY_REQUESTS)).retryable());
        assertTrue(classifier.classify(new HttpServerErrorException(HttpStatus.BAD_GATEWAY)).retryable());
    }

    @Test
    void invalidRequestsAndRejectedResponsesEscalateWithoutRetry() {
        assertFalse(classifier.classify(new HttpClientErrorException(HttpStatus.BAD_REQUEST)).retryable());
        assertFalse(classifier.classify(new IllegalStateException("identity mismatch")).retryable());
    }
}
