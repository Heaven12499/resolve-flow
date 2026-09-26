package com.resolveflow.business.action;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.resolveflow.business.domain.ApprovalTask;
import com.resolveflow.business.domain.BusinessActionExecution;
import com.resolveflow.business.repository.BusinessActionExecutionRepository;
import org.springframework.stereotype.Service;
import java.util.Map;

@Service
public class BusinessActionService {
    private final BusinessActionExecutionRepository executions;
    private final BusinessActionGateway gateway;
    private final ObjectMapper objectMapper;

    public BusinessActionService(BusinessActionExecutionRepository executions,
                                 BusinessActionGateway gateway, ObjectMapper objectMapper) {
        this.executions = executions;
        this.gateway = gateway;
        this.objectMapper = objectMapper;
    }

    public BusinessActionExecution issueCoupon(ApprovalTask approval, int amount, String operator) {
        String key = "approval:" + approval.getId() + ":issue_coupon";
        var existing = executions.findByIdempotencyKey(key);
        if (existing.isPresent()) return existing.get();

        BusinessActionExecution execution = executions.saveAndFlush(new BusinessActionExecution(
                approval.getTicket(), approval, key, "issue_coupon",
                json(Map.of("amount", amount, "operator", operator))));
        var result = gateway.issueCoupon(key, amount, String.valueOf(approval.getTicket().getCustomer().getId()));
        execution.succeed(result.externalReference(), json(Map.of(
                "provider", result.provider(), "provider_status", result.status())));
        return execution;
    }

    public BusinessActionExecution registerRefund(ApprovalTask approval, String operator, String reason) {
        String key = "approval:" + approval.getId() + ":refund";
        var existing = executions.findByIdempotencyKey(key);
        if (existing.isPresent()) return existing.get();

        BusinessActionExecution execution = executions.saveAndFlush(new BusinessActionExecution(
                approval.getTicket(), approval, key, "refund",
                json(Map.of("operator", operator, "reason", reason))));
        execution.requireManualExecution(json(Map.of(
                "provider", "manual-demo", "next_step", "finance_or_payment_gateway")));
        return execution;
    }

    private String json(Object value) {
        try { return objectMapper.writeValueAsString(value); }
        catch (Exception exception) { throw new IllegalStateException("业务动作数据序列化失败"); }
    }
}
