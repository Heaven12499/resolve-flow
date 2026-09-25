package com.resolveflow.business.ai;

import com.fasterxml.jackson.databind.JsonNode;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.http.MediaType;
import org.springframework.http.client.MultipartBodyBuilder;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;
import org.springframework.web.multipart.MultipartFile;
import java.io.IOException;

@Component
public class AiAdminClient {
    private final RestClient client;
    public AiAdminClient(RestClient aiRestClient) { this.client = aiRestClient; }

    public JsonNode listAgentRuns(int limit) {
        return require(client.get().uri(uri -> uri.path("/internal/v1/admin/agent-runs")
                .queryParam("limit", limit).build()).retrieve().body(JsonNode.class));
    }
    public JsonNode listKnowledgeDocuments() {
        return require(client.get().uri("/internal/v1/admin/knowledge/documents").retrieve().body(JsonNode.class));
    }
    public JsonNode createKnowledgeDocument(JsonNode payload) {
        return require(client.post().uri("/internal/v1/admin/knowledge/documents")
                .body(payload).retrieve().body(JsonNode.class));
    }
    public JsonNode updateKnowledgeDocument(long id, JsonNode payload) {
        return require(client.patch().uri("/internal/v1/admin/knowledge/documents/{id}", id)
                .body(payload).retrieve().body(JsonNode.class));
    }
    public JsonNode reindexKnowledge() {
        return require(client.post().uri("/internal/v1/admin/knowledge/reindex")
                .retrieve().body(JsonNode.class));
    }
    public JsonNode ingestKnowledge(MultipartFile file, String category, String version) throws IOException {
        var body = new MultipartBodyBuilder();
        body.part("file", new ByteArrayResource(file.getBytes()) {
            @Override public String getFilename() { return file.getOriginalFilename(); }
        }).contentType(file.getContentType() == null ? MediaType.APPLICATION_OCTET_STREAM : MediaType.parseMediaType(file.getContentType()));
        body.part("category", category);
        body.part("version", version);
        return require(client.post().uri("/internal/v1/admin/knowledge/documents/ingest")
                .contentType(MediaType.MULTIPART_FORM_DATA).body(body.build())
                .retrieve().body(JsonNode.class));
    }
    private JsonNode require(JsonNode response) {
        if (response == null) throw new IllegalStateException("AI service returned an empty admin response");
        return response;
    }
}
