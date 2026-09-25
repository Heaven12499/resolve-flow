package com.resolveflow.business.api;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import java.time.Instant;
import java.util.List;
import java.util.Map;

public final class TicketDtos {
    private TicketDtos() {}
    public record CreateTicketRequest(
            @NotBlank @Size(max = 64) String orderNo,
            @NotBlank @Size(min = 2, max = 2000) String content,
            @Size(max = 255) String title) {}

    public record MessageView(Long id, String senderType, String content, Instant createdAt) {}
    public record ApprovalView(Long id, String taskType, String status, Map<String, Object> proposedData,
                               Map<String, Object> decisionData, Instant createdAt, Instant decidedAt) {}
    public record TicketView(
            Long id, String ticketNo, Long customerId, Long orderId, String title, String content,
            String intent, String priority, String riskLevel, String status, long version,
            Instant createdAt, Instant updatedAt, List<MessageView> messages,
            List<ApprovalView> approvalTasks, List<Object> auditLogs, List<Object> agentRuns,
            List<Object> evidenceItems) {}
}
