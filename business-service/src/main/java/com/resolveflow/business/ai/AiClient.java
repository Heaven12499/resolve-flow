package com.resolveflow.business.ai;

import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
public class AiClient {
    private final RestClient client;
    public AiClient(RestClient aiRestClient) { this.client = aiRestClient; }

    public AiContracts.AnalyzeResult analyze(AiContracts.AnalyzeRequest request) {
        var result = client.post().uri("/internal/v1/ai/analyze")
                .body(request).retrieve().body(AiContracts.AnalyzeResult.class);
        if (result == null) throw new IllegalStateException("AI service returned an empty response");
        if (!request.taskId().equals(result.taskId()) || !request.ticketId().equals(result.ticketId())) {
            throw new IllegalStateException("AI response identity mismatch");
        }
        return result;
    }
}
