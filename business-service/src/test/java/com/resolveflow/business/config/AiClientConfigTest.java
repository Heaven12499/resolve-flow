package com.resolveflow.business.config;

import org.junit.jupiter.api.Test;
import org.springframework.web.client.RestClient;
import java.time.Duration;
import static org.junit.jupiter.api.Assertions.assertThrows;

class AiClientConfigTest {
    @Test
    void rejectsShortInternalServiceToken() {
        var config = new AiClientConfig();
        assertThrows(IllegalStateException.class, () -> config.aiRestClient(
                RestClient.builder(), "http://localhost:8000", "too-short",
                Duration.ofSeconds(1), Duration.ofSeconds(1)));
    }
}
