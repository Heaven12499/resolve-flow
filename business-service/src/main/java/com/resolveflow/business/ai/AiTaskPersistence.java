package com.resolveflow.business.ai;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.resolveflow.business.domain.*;
import com.resolveflow.business.repository.*;
import jakarta.persistence.EntityNotFoundException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.data.domain.PageRequest;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.Optional;

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
    private final AiRetryPolicy retryPolicy;
    private final Duration leaseDuration;
    private final AiTaskMetrics metrics;

    public AiTaskPersistence(AiTaskRepository tasks, TicketRepository tickets, TicketMessageRepository messages,
                             LogisticsEventRepository logistics, ApprovalTaskRepository approvals,
                             TicketEvidenceRepository evidence,
                             AuditLogRepository audits, ObjectMapper objectMapper,
                             AiRetryPolicy retryPolicy, AiTaskMetrics metrics,
                             @Value("${resolveflow.ai.worker.lease-duration:45s}") Duration leaseDuration) {
        this.tasks = tasks; this.tickets = tickets; this.messages = messages; this.logistics = logistics;
        this.approvals = approvals; this.evidence = evidence; this.audits = audits; this.objectMapper = objectMapper;
        this.retryPolicy = retryPolicy; this.metrics = metrics; this.leaseDuration = leaseDuration;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public Optional<AiContracts.AnalyzeRequest> prepare(String taskId) {
        AiTask task = tasks.findByTaskIdForUpdate(taskId)
                .orElseThrow(() -> new EntityNotFoundException("AI task not found"));
        Instant now = Instant.now();
        if (task.getStatus() != AiTaskStatus.PENDING || task.getNextAttemptAt().isAfter(now)) {
            return Optional.empty();
        }
        task.start(now, leaseDuration);
        metrics.claimed();
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
        return Optional.of(new AiContracts.AnalyzeRequest(
                task.getTaskId(), ticket.getId(), task.getBusinessVersion(),
                new AiContracts.TicketSnapshot(ticket.getTicketNo(), ticket.getTitle(), ticket.getContent()),
                new AiContracts.OrderSnapshot(order.getOrderNo(), order.getProductName(), order.getAmount(),
                        order.getStatus(), order.getShippedAt(), order.getPromisedDeliveryAt()),
                timeline, messageSnapshots, evidenceSnapshots));
    }

    @Transactional
    public boolean apply(AiContracts.AnalyzeResult result) throws JsonProcessingException {
        AiTask task = tasks.findByTaskIdForUpdate(result.taskId())
                .orElseThrow(() -> new EntityNotFoundException("AI task not found"));
        Ticket ticket = tickets.findById(result.ticketId()).orElseThrow(() -> new EntityNotFoundException("Ticket not found"));
        if (task.getStatus() != AiTaskStatus.RUNNING) throw new IllegalStateException("AI task is not running");
        if (result.businessVersion() != task.getBusinessVersion() || ticket.getVersion() != task.getBusinessVersion()) {
            task.fail("STALE_BUSINESS_VERSION", "AI result targets an outdated ticket version");
            if (ticket.getStatus() == TicketStatus.AI_QUEUED) ticket.routeAiFailureToHumanReview();
            audits.save(new AuditLog(ticket, "ai_task_escalated_to_human", "system",
                    json(Map.of("error_code", "STALE_BUSINESS_VERSION", "task_id", result.taskId()))));
            metrics.escalated();
            return false;
        }

        TicketStatus nextStatus = switch (result.recommendedAction()) {
            case "QUERY_LOGISTICS" -> TicketStatus.RESOLVED;
            case "REQUEST_COUPON_APPROVAL" -> TicketStatus.PENDING_APPROVAL;
            case "REQUEST_CUSTOMER_EVIDENCE" -> TicketStatus.WAITING_CUSTOMER;
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
                Map<String, Object> proposed = new java.util.LinkedHashMap<>();
                proposed.put("ai_task_id", result.taskId());
                proposed.put("confidence", result.confidence());
                proposed.put("reason", "AI建议主管复核，未执行退款");
                proposed.put("required_evidence", java.util.List.of("订单信息", "商品问题照片或视频", "签收及使用情况"));
                if (result.reviewPackage() != null) proposed.put("review_package", result.reviewPackage());
                approvals.save(new ApprovalTask(ticket, "refund_review", objectMapper.writeValueAsString(proposed)));
            }
        }
        String resultJson = objectMapper.writeValueAsString(result);
        task.succeed(resultJson, result.modelSource());
        audits.save(new AuditLog(ticket, "apply_ai_recommendation", "system", resultJson));
        return true;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void recordFailure(String taskId, String errorCode, String detail, boolean retryable) {
        AiTask task = tasks.findByTaskIdForUpdate(taskId)
                .orElseThrow(() -> new EntityNotFoundException("AI task not found"));
        if (task.getStatus() != AiTaskStatus.RUNNING) return;
        Ticket ticket = task.getTicket();
        String safeDetail = detail == null ? errorCode : detail.substring(0, Math.min(detail.length(), 500));
        if (retryPolicy.shouldRetry(task.getAttemptCount(), retryable)) {
            Duration delay = retryPolicy.backoffFor(task.getAttemptCount());
            Instant retryAt = Instant.now().plus(delay);
            task.scheduleRetry(errorCode, safeDetail, retryAt);
            metrics.retryScheduled();
            audits.save(new AuditLog(ticket, "ai_task_retry_scheduled", "system", json(Map.of(
                    "task_id", taskId, "attempt", task.getAttemptCount(), "retry_at", retryAt.toString(),
                    "error_code", errorCode))));
            return;
        }
        task.fail(errorCode, safeDetail);
        if (ticket.getVersion() == task.getBusinessVersion() && ticket.getStatus() == TicketStatus.AI_QUEUED) {
            ticket.routeAiFailureToHumanReview();
            audits.save(new AuditLog(ticket, "ai_task_escalated_to_human", "system", json(Map.of(
                    "task_id", taskId, "attempts", task.getAttemptCount(), "error_code", errorCode))));
            metrics.escalated();
        }
    }

    @Transactional(readOnly = true)
    public List<String> findDueTaskIds(int batchSize) {
        return tasks.findDueTaskIds(AiTaskStatus.PENDING, Instant.now(), PageRequest.of(0, batchSize));
    }

    @Transactional
    public int recoverExpiredLeases(int batchSize) {
        Instant now = Instant.now();
        var expired = tasks.findExpiredLeasesForUpdate(
                AiTaskStatus.RUNNING, now, PageRequest.of(0, batchSize));
        for (AiTask task : expired) {
            Ticket ticket = task.getTicket();
            if (retryPolicy.shouldRetry(task.getAttemptCount(), true)) {
                Instant retryAt = now.plus(retryPolicy.backoffFor(task.getAttemptCount()));
                task.recoverExpiredLease(now, retryAt);
                metrics.leaseRecovered();
                audits.save(new AuditLog(ticket, "ai_task_lease_recovered", "system", json(Map.of(
                        "task_id", task.getTaskId(), "attempt", task.getAttemptCount(),
                        "retry_at", retryAt.toString()))));
            } else {
                task.fail("EXECUTION_LEASE_EXHAUSTED", "AI worker lease expired after maximum attempts");
                if (ticket.getVersion() == task.getBusinessVersion()
                        && ticket.getStatus() == TicketStatus.AI_QUEUED) {
                    ticket.routeAiFailureToHumanReview();
                    metrics.escalated();
                }
                audits.save(new AuditLog(ticket, "ai_task_escalated_to_human", "system", json(Map.of(
                        "task_id", task.getTaskId(), "attempts", task.getAttemptCount(),
                        "error_code", "EXECUTION_LEASE_EXHAUSTED"))));
            }
        }
        return expired.size();
    }

    private String json(Map<String, Object> value) {
        try { return objectMapper.writeValueAsString(value); }
        catch (JsonProcessingException exception) { return "{\"serialization_error\":true}"; }
    }
}
