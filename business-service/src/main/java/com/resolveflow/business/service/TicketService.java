package com.resolveflow.business.service;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.resolveflow.business.ai.AiTaskRequested;
import com.resolveflow.business.api.TicketDtos;
import com.resolveflow.business.domain.*;
import com.resolveflow.business.repository.*;
import jakarta.persistence.EntityNotFoundException;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.*;

@Service
public class TicketService {
    private final TicketRepository tickets;
    private final TicketMessageRepository messages;
    private final BusinessOrderRepository orders;
    private final ApprovalTaskRepository approvals;
    private final AiTaskRepository aiTasks;
    private final TicketEvidenceRepository evidence;
    private final AuditLogRepository audits;
    private final BusinessActionExecutionRepository businessActions;
    private final ApplicationEventPublisher events;
    private final ObjectMapper objectMapper;

    public TicketService(TicketRepository tickets, TicketMessageRepository messages,
                         BusinessOrderRepository orders, ApprovalTaskRepository approvals,
                         AiTaskRepository aiTasks, TicketEvidenceRepository evidence, AuditLogRepository audits,
                         BusinessActionExecutionRepository businessActions,
                         ApplicationEventPublisher events, ObjectMapper objectMapper) {
        this.tickets = tickets; this.messages = messages; this.orders = orders; this.approvals = approvals;
        this.aiTasks = aiTasks; this.evidence = evidence; this.audits = audits;
        this.businessActions = businessActions;
        this.events = events; this.objectMapper = objectMapper;
    }

    @Transactional
    public TicketDtos.TicketView create(TicketDtos.CreateTicketRequest request, String actor, String idempotencyKey) {
        String normalizedKey = normalizeIdempotencyKey(idempotencyKey);
        String requestHash = intakeRequestHash(request);
        if (normalizedKey != null) {
            Optional<Ticket> existing = tickets.findByIntakeIdempotencyKey(normalizedKey);
            if (existing.isPresent()) {
                if (!requestHash.equals(existing.get().getIntakeRequestHash())) {
                    throw new IllegalStateException("同一幂等键不能用于不同的工单请求");
                }
                return toView(existing.get());
            }
        }
        BusinessOrder order = orders.findByOrderNo(request.orderNo())
                .orElseThrow(() -> new EntityNotFoundException("订单不存在"));
        String ticketNo = "TK" + DateTimeFormatter.ofPattern("yyyyMMddHHmmss").withZone(ZoneOffset.UTC)
                .format(java.time.Instant.now()) + UUID.randomUUID().toString().substring(0, 6).toUpperCase();
        String title = request.title() == null || request.title().isBlank()
                ? request.content().substring(0, Math.min(50, request.content().length())) : request.title();
        Ticket ticket = new Ticket(ticketNo, order.getCustomer(), order, title, request.content());
        ticket.bindIntakeRequest(normalizedKey, requestHash);
        ticket = tickets.saveAndFlush(ticket);
        messages.save(new TicketMessage(ticket, "customer", request.content()));
        audits.save(new AuditLog(ticket, "create_ticket", actor, "{\"order_no\":\"" + order.getOrderNo() + "\"}"));
        queue(ticket);
        return toView(ticket);
    }

    private String normalizeIdempotencyKey(String value) {
        if (value == null || value.isBlank()) return null;
        String normalized = value.trim();
        if (normalized.length() > 120) throw new IllegalStateException("幂等键长度不能超过 120 个字符");
        return normalized;
    }

    private String intakeRequestHash(TicketDtos.CreateTicketRequest request) {
        String canonical = request.orderNo().trim() + "\n"
                + Objects.toString(request.title(), "").trim() + "\n" + request.content().trim();
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256").digest(canonical.getBytes(StandardCharsets.UTF_8));
            return HexFormat.of().formatHex(digest);
        } catch (Exception exception) {
            throw new IllegalStateException("无法生成工单请求摘要");
        }
    }

    @Transactional(readOnly = true)
    public TicketDtos.TicketPage list(int page, int size, String status, String keyword) {
        int safePage = Math.max(page, 0);
        int safeSize = Math.min(Math.max(size, 1), 100);
        TicketStatus internalStatus = parseStatus(status);
        String normalizedKeyword = keyword == null || keyword.isBlank() ? null : keyword.trim();
        var result = tickets.search(internalStatus, normalizedKeyword,
                PageRequest.of(safePage, safeSize, Sort.by(Sort.Direction.DESC, "createdAt")));
        List<Long> ticketIds = result.getContent().stream().map(Ticket::getId).toList();
        Map<Long, String> decisionSources = new HashMap<>();
        if (!ticketIds.isEmpty()) {
            aiTasks.findByTicketIdInAndStatusOrderByFinishedAtDesc(ticketIds, AiTaskStatus.SUCCEEDED)
                    .forEach(task -> decisionSources.putIfAbsent(task.getTicket().getId(), task.getModelSource()));
        }
        return new TicketDtos.TicketPage(result.getContent().stream()
                .map(ticket -> toSummary(ticket, decisionSources.get(ticket.getId()))).toList(),
                result.getNumber(), result.getSize(), result.getTotalElements(), result.getTotalPages());
    }

    @Transactional(readOnly = true)
    public TicketDtos.TicketView get(Long id) {
        return toView(find(id));
    }

    @Transactional
    public TicketDtos.TicketView retry(Long id, String actor) {
        Ticket ticket = find(id);
        if (ticket.getStatus() != TicketStatus.AI_FAILED && ticket.getStatus() != TicketStatus.WAITING_CUSTOMER) {
            throw new IllegalStateException("只有 AI_FAILED 或 WAITING_CUSTOMER 状态可以重新处理");
        }
        audits.save(new AuditLog(ticket, "retry_ai_task", actor, null));
        queue(ticket);
        return toView(ticket);
    }

    @Transactional
    public TicketDtos.TicketView addCustomerMessage(Long id, TicketDtos.AddMessageRequest request, String actor) {
        Ticket ticket = find(id);
        if (ticket.getStatus() != TicketStatus.WAITING_CUSTOMER) {
            throw new IllegalStateException("工单当前不在等待客户补充材料状态");
        }
        TicketMessage message = messages.saveAndFlush(new TicketMessage(ticket, "customer", request.content()));
        int accepted = 0;
        for (var attachment : request.attachments()) {
            String hash = attachment.sha256().toLowerCase();
            if (evidence.existsByTicketIdAndSha256(ticket.getId(), hash)) continue;
            evidence.save(new TicketEvidence(ticket, ticket.getOrder(), message, attachment.fileName(),
                    attachment.mediaType(), attachment.storageUri(), hash));
            accepted++;
        }
        audits.save(new AuditLog(ticket, "customer_evidence_received", actor,
                "{\"accepted_attachments\":" + accepted + "}"));
        queue(ticket);
        return toView(ticket);
    }

    private void queue(Ticket ticket) {
        ticket.retryAi();
        tickets.saveAndFlush(ticket);
        String idempotencyKey = "ticket:" + ticket.getId() + ":version:" + ticket.getVersion();
        if (aiTasks.findByIdempotencyKey(idempotencyKey).isPresent()) {
            throw new IllegalStateException("该工单版本已经创建过 AI 任务");
        }
        String taskId = "AIT-" + UUID.randomUUID().toString().replace("-", "").substring(0, 20).toUpperCase();
        aiTasks.save(new AiTask(taskId, ticket, idempotencyKey, ticket.getVersion()));
        events.publishEvent(new AiTaskRequested(taskId));
    }

    private Ticket find(Long id) {
        return tickets.findById(id).orElseThrow(() -> new EntityNotFoundException("工单不存在"));
    }

    private TicketDtos.TicketView toView(Ticket ticket) {
        Optional<AiTask> latestAiTask = aiTasks
                .findFirstByTicketIdAndStatusOrderByFinishedAtDesc(ticket.getId(), AiTaskStatus.SUCCEEDED);
        String decisionSource = latestAiTask.map(AiTask::getModelSource).orElse(null);
        List<Object> agentRuns = latestAiTask
                .map(AiTask::getResultPayload)
                .map(payload -> readJsonList(payload, "execution_trace"))
                .orElseGet(List::of);
        var messageViews = messages.findByTicketIdOrderByCreatedAtAsc(ticket.getId()).stream()
                .map(item -> new TicketDtos.MessageView(item.getId(), item.getSenderType(), item.getContent(), item.getCreatedAt()))
                .toList();
        var approvalViews = approvals.findByTicketIdOrderByCreatedAtAsc(ticket.getId()).stream()
                .map(item -> new TicketDtos.ApprovalView(item.getId(), item.getTaskType(), item.getStatus(),
                        readJson(item.getProposedData()), readJson(item.getDecisionData()), item.getCreatedAt(), item.getDecidedAt()))
                .toList();
        var evidenceViews = evidence.findByTicketIdOrderByCreatedAtAsc(ticket.getId()).stream()
                .map(item -> new TicketDtos.EvidenceView(item.getId(), item.getOrder().getId(), item.getMessage().getId(),
                        item.getFileName(), item.getMediaType(), item.getStorageUri(), item.getSha256(),
                        item.getUploadedBy(), item.getCreatedAt()))
                .toList();
        var auditViews = audits.findByTicketIdOrderByCreatedAtAsc(ticket.getId()).stream()
                .map(item -> new TicketDtos.AuditView(item.getId(), item.getAction(), item.getOperatorType(),
                        null, readJson(item.getDetailsJson()), item.getCreatedAt()))
                .toList();
        var businessActionViews = businessActions.findByTicketIdOrderByCreatedAtAsc(ticket.getId()).stream()
                .map(item -> new TicketDtos.BusinessActionView(item.getId(), item.getActionType(), item.getStatus(),
                        item.getIdempotencyKey(), readJson(item.getRequestJson()), readJson(item.getResultJson()),
                        item.getExternalReference(), item.getErrorMessage(), item.getAttemptCount(),
                        item.getCreatedAt(), item.getUpdatedAt()))
                .toList();
        return new TicketDtos.TicketView(ticket.getId(), ticket.getTicketNo(), ticket.getCustomer().getId(),
                ticket.getOrder().getId(), ticket.getTitle(), ticket.getContent(), ticket.getIntent(),
                ticket.getPriority(), ticket.getRiskLevel(), decisionSource,
                externalStatus(ticket.getStatus()), ticket.getVersion(),
                ticket.getCreatedAt(), ticket.getUpdatedAt(), messageViews, approvalViews,
                auditViews, agentRuns, evidenceViews, businessActionViews);
    }

    private TicketDtos.TicketSummary toSummary(Ticket ticket, String decisionSource) {
        return new TicketDtos.TicketSummary(ticket.getId(), ticket.getTicketNo(), ticket.getCustomer().getId(),
                ticket.getOrder().getId(), ticket.getTitle(), ticket.getContent(), ticket.getIntent(),
                ticket.getPriority(), ticket.getRiskLevel(), decisionSource, externalStatus(ticket.getStatus()),
                ticket.getVersion(), ticket.getCreatedAt(), ticket.getUpdatedAt());
    }

    private TicketStatus parseStatus(String status) {
        if (status == null || status.isBlank()) return null;
        return switch (status.trim().toLowerCase(Locale.ROOT)) {
            case "queued" -> TicketStatus.AI_QUEUED;
            case "processing" -> TicketStatus.AI_PROCESSING;
            case "escalated" -> TicketStatus.HUMAN_REVIEW;
            case "failed" -> TicketStatus.AI_FAILED;
            default -> {
                try { yield TicketStatus.valueOf(status.trim().toUpperCase(Locale.ROOT)); }
                catch (IllegalArgumentException exception) { throw new IllegalStateException("不支持的工单状态"); }
            }
        };
    }

    private String externalStatus(TicketStatus status) {
        return switch (status) {
            case AI_QUEUED -> "queued";
            case AI_PROCESSING -> "processing";
            case HUMAN_REVIEW -> "escalated";
            case AI_FAILED -> "failed";
            default -> status.name().toLowerCase();
        };
    }

    private Map<String, Object> readJson(String value) {
        if (value == null || value.isBlank()) return null;
        try { return objectMapper.readValue(value, new TypeReference<>() {}); }
        catch (Exception ignored) { return Map.of("raw", value); }
    }

    private List<Object> readJsonList(String value, String field) {
        if (value == null || value.isBlank()) return List.of();
        try {
            var root = objectMapper.readTree(value);
            var node = root.get(field);
            if (node == null || !node.isArray()) return List.of();
            return objectMapper.convertValue(node, new TypeReference<List<Object>>() {});
        } catch (Exception ignored) {
            return List.of();
        }
    }
}
