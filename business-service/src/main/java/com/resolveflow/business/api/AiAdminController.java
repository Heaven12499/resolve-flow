package com.resolveflow.business.api;

import com.fasterxml.jackson.databind.JsonNode;
import com.resolveflow.business.ai.AiAdminClient;
import com.resolveflow.business.ai.AiTaskMonitor;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;
import java.io.IOException;

@RestController
@RequestMapping("/api")
@PreAuthorize("hasRole('ADMIN')")
public class AiAdminController {
    private final AiAdminClient client;
    private final AiTaskMonitor taskMonitor;
    public AiAdminController(AiAdminClient client, AiTaskMonitor taskMonitor) {
        this.client = client; this.taskMonitor = taskMonitor;
    }

    @GetMapping("/agent-runs")
    public JsonNode agentRuns(@RequestParam(defaultValue = "100") @Min(1) @Max(300) int limit) {
        return client.listAgentRuns(limit);
    }
    @GetMapping("/ai-tasks")
    public java.util.List<AiTaskMonitor.TaskView> aiTasks(
            @RequestParam(defaultValue = "100") @Min(1) @Max(300) int limit) {
        return taskMonitor.latest(limit);
    }
    @GetMapping("/knowledge/documents")
    public JsonNode documents() { return client.listKnowledgeDocuments(); }
    @PostMapping("/knowledge/documents")
    public JsonNode create(@RequestBody JsonNode payload) { return client.createKnowledgeDocument(payload); }
    @PatchMapping("/knowledge/documents/{id}")
    public JsonNode update(@PathVariable long id, @RequestBody JsonNode payload) {
        return client.updateKnowledgeDocument(id, payload);
    }
    @PostMapping("/knowledge/reindex")
    public JsonNode reindex() { return client.reindexKnowledge(); }
    @PostMapping(value = "/knowledge/documents/ingest", consumes = "multipart/form-data")
    public JsonNode ingest(@RequestPart("file") MultipartFile file,
                           @RequestParam(defaultValue = "after_sales") String category,
                           @RequestParam(defaultValue = "v1.0") String version) throws IOException {
        return client.ingestKnowledge(file, category, version);
    }
}
