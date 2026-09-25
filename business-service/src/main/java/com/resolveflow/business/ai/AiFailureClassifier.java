package com.resolveflow.business.ai;

import org.springframework.stereotype.Component;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClientResponseException;

@Component
public class AiFailureClassifier {
    public Failure classify(Exception exception) {
        if (exception instanceof RestClientResponseException response) {
            int status = response.getStatusCode().value();
            boolean retryable = status == 408 || status == 409 || status == 425 || status == 429 || status >= 500;
            return new Failure("AI_HTTP_" + status, message(exception), retryable);
        }
        if (exception instanceof ResourceAccessException) {
            return new Failure("AI_SERVICE_UNAVAILABLE", message(exception), true);
        }
        if (exception instanceof IllegalArgumentException || exception instanceof IllegalStateException) {
            return new Failure("AI_RESPONSE_REJECTED", message(exception), false);
        }
        return new Failure(exception.getClass().getSimpleName(), message(exception), true);
    }

    private String message(Exception exception) {
        String value = exception.getMessage();
        return value == null || value.isBlank() ? exception.getClass().getSimpleName() : value;
    }

    public record Failure(String code, String detail, boolean retryable) {}
}
