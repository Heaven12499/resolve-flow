package com.resolveflow.business.ai;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;

public final class AiContracts {
    private AiContracts() {}
    public record TicketSnapshot(String ticketNo, String title, String content) {}
    public record OrderSnapshot(String orderNo, String productName, BigDecimal amount, String status,
                                Instant shippedAt, Instant promisedDeliveryAt) {}
    public record LogisticsSnapshot(Long eventId, String status, String description, Instant occurredAt) {}
    public record MessageSnapshot(String senderType, String content, Instant createdAt) {}
    public record EvidenceSnapshot(Long evidenceId, String fileName, String mediaType, String storageUri, String sha256) {}
    public record AnalyzeRequest(String taskId, Long ticketId, long businessVersion, TicketSnapshot ticket,
                                 OrderSnapshot order, List<LogisticsSnapshot> logisticsTimeline,
                                 List<MessageSnapshot> messages, List<EvidenceSnapshot> evidence) {}
    public record EvidenceReference(String type, String reference) {}
    public record AgentExecutionStep(int sequence, String agentName, String status, String provider,
                                     String model, java.util.Map<String, Object> inputData,
                                     java.util.Map<String, Object> outputData, String error,
                                     long durationMs, Instant startedAt, Instant finishedAt) {}
    public record AnalyzeResult(String taskId, Long ticketId, long businessVersion, String status,
                                String intent, String priority, String riskLevel, String recommendedAction,
                                Integer suggestedCouponAmount, String replyDraft, double confidence,
                                boolean requiresHumanApproval, List<EvidenceReference> evidence,
                                String modelSource, String fallbackReason,
                                java.util.Map<String, Object> orchestrationPlan,
                                List<AgentExecutionStep> executionTrace,
                                List<java.util.Map<String, Object>> knowledgeSources,
                                java.util.Map<String, Object> reviewPackage) {}
}
