package com.resolveflow.business.service;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.resolveflow.business.ai.AiTaskRequested;
import com.resolveflow.business.api.TicketDtos;
import com.resolveflow.business.domain.*;
import com.resolveflow.business.repository.*;
import jakarta.persistence.EntityNotFoundException;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.*;

@Service
public class TicketService {
    private final TicketRepository tickets;
    private final TicketMessageRepository messages;
    private final BusinessOrderRepository orders;
    private final ApprovalTaskRepository approvals;
    private final AiTaskRepository aiTasks;
    private final AuditLogRepository audits;
    private final ApplicationEventPublisher events;
    private final ObjectMapper objectMapper;

    public TicketService(TicketRepository tickets, TicketMessageRepository messages,
                         BusinessOrderRepository orders, ApprovalTaskRepository approvals,
                         AiTaskRepository aiTasks, AuditLogRepository audits,
                         ApplicationEventPublisher events, ObjectMapper objectMapper) {
        this.tickets = tickets; this.messages = messages; this.orders = orders; this.approvals = approvals;
        this.aiTasks = aiTasks; this.audits = audits; this.events = events; this.objectMapper = objectMapper;
    }

    @Transactional
    public TicketDtos.TicketView create(TicketDtos.CreateTicketRequest request, String actor) {
        BusinessOrder order = orders.findByOrderNo(request.orderNo())
                .orElseThrow(() -> new EntityNotFoundException("订单不存在"));
        String ticketNo = "TK" + DateTimeFormatter.ofPattern("yyyyMMddHHmmss").withZone(ZoneOffset.UTC)
                .format(java.time.Instant.now()) + UUID.randomUUID().toString().substring(0, 6).toUpperCase();
        String title = request.title() == null || request.title().isBlank()
                ? request.content().substring(0, Math.min(50, request.content().length())) : request.title();
        Ticket ticket = tickets.saveAndFlush(new Ticket(ticketNo, order.getCustomer(), order, title, request.content()));
        messages.save(new TicketMessage(ticket, "customer", request.content()));
        audits.save(new AuditLog(ticket, "create_ticket", actor, "{\"order_no\":\"" + order.getOrderNo() + "\"}"));
        queue(ticket);
        return toView(ticket);
    }

    @Transactional(readOnly = true)
    public List<TicketDtos.TicketView> list() {
        return tickets.findAllByOrderByCreatedAtDesc().stream().map(this::toView).toList();
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
        var messageViews = messages.findByTicketIdOrderByCreatedAtAsc(ticket.getId()).stream()
                .map(item -> new TicketDtos.MessageView(item.getId(), item.getSenderType(), item.getContent(), item.getCreatedAt()))
                .toList();
        var approvalViews = approvals.findByTicketIdOrderByCreatedAtAsc(ticket.getId()).stream()
                .map(item -> new TicketDtos.ApprovalView(item.getId(), item.getTaskType(), item.getStatus(),
                        readJson(item.getProposedData()), readJson(item.getDecisionData()), item.getCreatedAt(), item.getDecidedAt()))
                .toList();
        return new TicketDtos.TicketView(ticket.getId(), ticket.getTicketNo(), ticket.getCustomer().getId(),
                ticket.getOrder().getId(), ticket.getTitle(), ticket.getContent(), ticket.getIntent(),
                ticket.getPriority(), ticket.getRiskLevel(), ticket.getStatus().name().toLowerCase(), ticket.getVersion(),
                ticket.getCreatedAt(), ticket.getUpdatedAt(), messageViews, approvalViews,
                List.of(), List.of(), List.of());
    }

    private Map<String, Object> readJson(String value) {
        if (value == null || value.isBlank()) return null;
        try { return objectMapper.readValue(value, new TypeReference<>() {}); }
        catch (Exception ignored) { return Map.of("raw", value); }
    }
}
