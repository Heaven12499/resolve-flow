package com.resolveflow.business.ai;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.resolveflow.business.domain.*;
import com.resolveflow.business.repository.*;
import jakarta.persistence.EntityNotFoundException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.util.Map;

@Service
public class AiTaskPersistence {
    private final AiTaskRepository tasks;
    private final TicketRepository tickets;
    private final TicketMessageRepository messages;
    private final LogisticsEventRepository logistics;
    private final ApprovalTaskRepository approvals;
    private final TicketEvidenceRepository evidence;
    private final AuditLogRepository audits;
    private final ObjectMapper objectMapper;

    public AiTaskPersistence(AiTaskRepository tasks, TicketRepository tickets, TicketMessageRepository messages,
                             LogisticsEventRepository logistics, ApprovalTaskRepository approvals,
                             TicketEvidenceRepository evidence,
                             AuditLogRepository audits, ObjectMapper objectMapper) {
        this.tasks = tasks; this.tickets = tickets; this.messages = messages; this.logistics = logistics;
        this.approvals = approvals; this.evidence = evidence; this.audits = audits; this.objectMapper = objectMapper;
    }

    @Transactional
    public AiContracts.AnalyzeRequest prepare(String taskId) {
        AiTask task = tasks.findByTaskId(taskId).orElseThrow(() -> new EntityNotFoundException("AI task not found"));
        if (task.getStatus() != AiTaskStatus.PENDING) throw new IllegalStateException("AI task is not pending");
        task.start();
        Ticket ticket = task.getTicket();
        BusinessOrder order = ticket.getOrder();
        var timeline = logistics.findByOrderIdOrderByOccurredAtAsc(order.getId()).stream()
                .map(item -> new AiContracts.LogisticsSnapshot(item.getId(), item.getStatus(), item.getDescription(), item.getOccurredAt()))
                .toList();
        var messageSnapshots = messages.findByTicketIdOrderByCreatedAtAsc(ticket.getId()).stream()
                .map(item -> new AiContracts.MessageSnapshot(item.getSenderType(), item.getContent(), item.getCreatedAt()))
                .toList();
        var evidenceSnapshots = evidence.findByTicketIdOrderByCreatedAtAsc(ticket.getId()).stream()
                .map(item -> new AiContracts.EvidenceSnapshot(item.getId(), item.getFileName(), item.getMediaType(),
                        item.getStorageUri(), item.getSha256()))
                .toList();
        return new AiContracts.AnalyzeRequest(
                task.getTaskId(), ticket.getId(), task.getBusinessVersion(),
                new AiContracts.TicketSnapshot(ticket.getTitle(), ticket.getContent()),
                new AiContracts.OrderSnapshot(order.getOrderNo(), order.getProductName(), order.getAmount(),
                        order.getStatus(), order.getShippedAt(), order.getPromisedDeliveryAt()),
                timeline, messageSnapshots, evidenceSnapshots);
    }

    @Transactional
    public void apply(AiContracts.AnalyzeResult result) throws JsonProcessingException {
        AiTask task = tasks.findByTaskId(result.taskId()).orElseThrow(() -> new EntityNotFoundException("AI task not found"));
        Ticket ticket = tickets.findById(result.ticketId()).orElseThrow(() -> new EntityNotFoundException("Ticket not found"));
        if (task.getStatus() != AiTaskStatus.RUNNING) throw new IllegalStateException("AI task is not running");
        if (result.businessVersion() != task.getBusinessVersion() || ticket.getVersion() != task.getBusinessVersion()) {
            task.fail("STALE_BUSINESS_VERSION");
            return;
        }

        TicketStatus nextStatus = switch (result.recommendedAction()) {
            case "QUERY_LOGISTICS" -> TicketStatus.RESOLVED;
            case "REQUEST_COUPON_APPROVAL" -> TicketStatus.PENDING_APPROVAL;
            case "ESCALATE_REFUND_REVIEW", "ESCALATE_TO_HUMAN" -> TicketStatus.HUMAN_REVIEW;
            default -> throw new IllegalArgumentException("Unsupported AI recommendation: " + result.recommendedAction());
        };
        ticket.applyAiResult(result.intent(), result.priority(), result.riskLevel(), nextStatus);
        messages.save(new TicketMessage(ticket, "assistant", result.replyDraft()));

        if ("REQUEST_COUPON_APPROVAL".equals(result.recommendedAction())) {
            if (result.suggestedCouponAmount() == null || result.suggestedCouponAmount() < 1
                    || result.suggestedCouponAmount() > 100) {
                throw new IllegalArgumentException("AI recommendation contains an invalid coupon amount");
            }
            if (!approvals.existsByTicketIdAndTaskTypeAndStatusIn(ticket.getId(), "coupon_compensation",
                    java.util.List.of("pending", "in_review"))) {
                approvals.save(new ApprovalTask(ticket, "coupon_compensation", objectMapper.writeValueAsString(Map.of(
                        "coupon_amount", result.suggestedCouponAmount(), "currency", "CNY",
                        "reason", "物流延迟补偿", "approval_level", "agent",
                        "ai_task_id", result.taskId(), "confidence", result.confidence()))));
            }
        } else if ("ESCALATE_REFUND_REVIEW".equals(result.recommendedAction())) {
            if (!approvals.existsByTicketIdAndTaskTypeAndStatusIn(ticket.getId(), "refund_review",
                    java.util.List.of("pending", "in_review"))) {
                approvals.save(new ApprovalTask(ticket, "refund_review", objectMapper.writeValueAsString(Map.of(
                        "ai_task_id", result.taskId(), "confidence", result.confidence(),
                        "reason", "AI建议主管复核，未执行退款",
                        "required_evidence", java.util.List.of("订单信息", "商品问题照片或视频", "签收及使用情况")))));
            }
        }
        String resultJson = objectMapper.writeValueAsString(result);
        task.succeed(resultJson);
        audits.save(new AuditLog(ticket, "apply_ai_recommendation", "system", resultJson));
    }

    @Transactional
    public void fail(String taskId, String errorCode) {
        AiTask task = tasks.findByTaskId(taskId).orElseThrow(() -> new EntityNotFoundException("AI task not found"));
        task.fail(errorCode);
        Ticket ticket = task.getTicket();
        if (ticket.getVersion() == task.getBusinessVersion() && ticket.getStatus() == TicketStatus.AI_QUEUED) {
            ticket.failAi();
            audits.save(new AuditLog(ticket, "ai_task_failed", "system", "{\"error_code\":\"" + errorCode + "\"}"));
        }
    }
}
