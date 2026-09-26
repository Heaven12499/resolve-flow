package com.resolveflow.business.service;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.resolveflow.business.action.BusinessActionService;
import com.resolveflow.business.api.ApprovalDtos;
import com.resolveflow.business.api.TicketDtos;
import com.resolveflow.business.domain.*;
import com.resolveflow.business.repository.*;
import jakarta.persistence.EntityNotFoundException;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.util.*;

@Service
public class ApprovalService {
    private final ApprovalTaskRepository approvals;
    private final TicketMessageRepository messages;
    private final AuditLogRepository audits;
    private final TicketService tickets;
    private final BusinessActionService businessActions;
    private final ObjectMapper objectMapper;

    public ApprovalService(ApprovalTaskRepository approvals, TicketMessageRepository messages,
                           AuditLogRepository audits, TicketService tickets, BusinessActionService businessActions,
                           ObjectMapper objectMapper) {
        this.approvals = approvals; this.messages = messages; this.audits = audits;
        this.tickets = tickets; this.businessActions = businessActions; this.objectMapper = objectMapper;
    }

    @Transactional(readOnly = true)
    public List<ApprovalDtos.ApprovalQueueView> list(Authentication actor) {
        boolean agentOnly = hasRole(actor, "AGENT") && !hasRole(actor, "SUPERVISOR") && !hasRole(actor, "ADMIN");
        return approvals.findByStatusInOrderByCreatedAtAsc(List.of("pending", "in_review")).stream()
                .filter(task -> !agentOnly || (task.getTaskType().equals("coupon_compensation")
                        && task.getStatus().equals("pending") && couponAmount(task) <= 5))
                .map(this::toQueueView).toList();
    }

    @Transactional
    public TicketDtos.TicketView approveCoupon(Long taskId, Authentication actor) {
        ApprovalTask task = pending(taskId);
        if (!task.getTaskType().equals("coupon_compensation")) throw new IllegalStateException("该任务不是优惠券补偿审批");
        int amount = couponAmount(task);
        if (amount <= 0 || amount > 100) throw new IllegalStateException("补偿金额不合法");
        if (amount > 5 && !hasRole(actor, "SUPERVISOR") && !hasRole(actor, "ADMIN")) {
            throw new AccessDeniedException("当前账号没有此补偿审批权限");
        }
        Ticket ticket = task.getTicket();
        BusinessActionExecution execution = businessActions.issueCoupon(task, amount, actor.getName());
        String couponCode = execution.getExternalReference();
        task.approve(json(Map.of("coupon_code", couponCode, "approved_by", actor.getName(),
                "business_action_id", execution.getId())));
        ticket.resolveFromHuman();
        messages.save(new TicketMessage(ticket, "agent", "您的" + amount + "元补偿优惠券已发放，券码：" + couponCode + "。"));
        audit(ticket, "approve_coupon", actor, Map.of("approval_task_id", taskId, "coupon_code", couponCode,
                "business_action_id", execution.getId()));
        return tickets.get(ticket.getId());
    }

    @Transactional
    public TicketDtos.TicketView reject(Long taskId, String reason, Authentication actor) {
        ApprovalTask task = pendingOrReview(taskId);
        if (task.getTaskType().equals("refund_review") && hasRole(actor, "AGENT")) {
            throw new AccessDeniedException("当前账号没有此审批权限");
        }
        String finalReason = reason == null || reason.isBlank() ? "不满足当前审批条件" : reason;
        task.reject(json(Map.of("rejected_by", actor.getName(), "reason", finalReason)));
        Ticket ticket = task.getTicket();
        ticket.resolveFromHuman();
        messages.save(new TicketMessage(ticket, "agent", "抱歉，本次申请未获批准。原因：" + finalReason + "。"));
        audit(ticket, "reject_approval", actor, Map.of("approval_task_id", taskId, "reason", finalReason));
        return tickets.get(ticket.getId());
    }

    @Transactional
    public TicketDtos.TicketView assignSupervisor(Long taskId, String reason, Authentication actor) {
        requireSupervisor(actor);
        ApprovalTask task = pending(taskId);
        if (!task.getTaskType().equals("refund_review")) throw new IllegalStateException("该任务不是退款复核任务");
        task.assign(json(Map.of("assigned_to", actor.getName(), "note", reason == null ? "已转主管复核" : reason)));
        Ticket ticket = task.getTicket();
        messages.save(new TicketMessage(ticket, "agent", "您的退款诉求已转交主管复核，我们将在核验材料后反馈处理结果。"));
        audit(ticket, "assign_refund_review", actor, Map.of("approval_task_id", taskId));
        return tickets.get(ticket.getId());
    }

    @Transactional
    public TicketDtos.TicketView reviewRefund(Long taskId, ApprovalDtos.RefundReviewRequest request, Authentication actor) {
        requireSupervisor(actor);
        ApprovalTask task = pendingOrReview(taskId);
        if (!task.getTaskType().equals("refund_review")) throw new IllegalStateException("该任务不是退款复核任务");
        Ticket ticket = task.getTicket();
        Map<String, Object> decision = new LinkedHashMap<>();
        decision.put("decision", request.decision()); decision.put("reason", request.reason());
        decision.put("reviewed_by", actor.getName());
        if (request.decision().equals("approve_refund")) {
            BusinessActionExecution execution = businessActions.registerRefund(task, actor.getName(), request.reason());
            decision.put("payment_execution", execution.getStatus());
            decision.put("business_action_id", execution.getId());
        }
        String message;
        if (request.decision().equals("request_evidence")) {
            task.requestEvidence(json(decision)); ticket.waitForCustomer();
            message = "为完成退款复核，请补充以下说明或材料：" + request.reason();
        } else if (request.decision().equals("approve_refund")) {
            task.approve(json(decision)); ticket.resolveFromHuman();
            message = "主管已通过退款复核，退款将由人工财务或支付系统按流程执行。";
        } else {
            task.reject(json(decision)); ticket.resolveFromHuman();
            message = "本次退款申请未获批准。复核说明：" + request.reason();
        }
        messages.save(new TicketMessage(ticket, "agent", message));
        audit(ticket, "review_refund_" + request.decision(), actor, decision);
        return tickets.get(ticket.getId());
    }

    private ApprovalTask pending(Long id) {
        ApprovalTask task = approvals.findByIdForUpdate(id)
                .orElseThrow(() -> new EntityNotFoundException("审批任务不存在"));
        if (!task.getStatus().equals("pending")) throw new IllegalStateException("该审批任务已被处理");
        return task;
    }
    private ApprovalTask pendingOrReview(Long id) {
        ApprovalTask task = approvals.findByIdForUpdate(id)
                .orElseThrow(() -> new EntityNotFoundException("审批任务不存在"));
        if (!Set.of("pending", "in_review").contains(task.getStatus())) throw new IllegalStateException("该审批任务已被处理");
        return task;
    }
    private int couponAmount(ApprovalTask task) {
        Object value = read(task.getProposedData()).get("coupon_amount");
        try { return Integer.parseInt(String.valueOf(value)); } catch (Exception ignored) { return -1; }
    }
    private void requireSupervisor(Authentication actor) {
        if (!hasRole(actor, "SUPERVISOR") && !hasRole(actor, "ADMIN")) throw new AccessDeniedException("需要主管权限");
    }
    private boolean hasRole(Authentication actor, String role) {
        return actor.getAuthorities().stream().anyMatch(a -> a.getAuthority().equals("ROLE_" + role));
    }
    private ApprovalDtos.ApprovalQueueView toQueueView(ApprovalTask task) {
        Ticket ticket = task.getTicket();
        String status = ticket.getStatus() == TicketStatus.HUMAN_REVIEW ? "escalated" : ticket.getStatus().name().toLowerCase();
        return new ApprovalDtos.ApprovalQueueView(task.getId(), task.getTaskType(), task.getStatus(),
                read(task.getProposedData()), read(task.getDecisionData()), task.getCreatedAt(), task.getDecidedAt(),
                ticket.getId(), ticket.getTicketNo(), ticket.getTitle(), ticket.getContent(), status, ticket.getRiskLevel());
    }
    private Map<String, Object> read(String value) {
        if (value == null || value.isBlank()) return null;
        try { return objectMapper.readValue(value, new TypeReference<>() {}); }
        catch (Exception exception) { throw new IllegalStateException("审批数据损坏"); }
    }
    private String json(Object value) {
        try { return objectMapper.writeValueAsString(value); }
        catch (Exception exception) { throw new IllegalStateException("审批数据序列化失败"); }
    }
    private void audit(Ticket ticket, String action, Authentication actor, Object details) {
        audits.save(new AuditLog(ticket, action, actor.getName(), json(details)));
    }
}
