package com.resolveflow.business.api;

import com.resolveflow.business.service.ApprovalService;
import jakarta.validation.Valid;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.*;
import java.util.List;

@RestController
@RequestMapping("/api")
public class ApprovalController {
    private final ApprovalService service;
    public ApprovalController(ApprovalService service) { this.service = service; }

    @GetMapping("/approvals")
    public List<ApprovalDtos.ApprovalQueueView> list(Authentication actor) { return service.list(actor); }

    @PostMapping("/tickets/{ticketId}/approve-coupon")
    public TicketDtos.TicketView approveCouponForTicket(@PathVariable Long ticketId, Authentication actor) {
        var task = service.list(actor).stream()
                .filter(item -> item.ticketId().equals(ticketId) && item.taskType().equals("coupon_compensation"))
                .findFirst().orElseThrow(() -> new IllegalStateException("没有待审批的优惠券补偿任务"));
        return service.approveCoupon(task.id(), actor);
    }

    @PostMapping("/approvals/{taskId}/approve-coupon")
    public TicketDtos.TicketView approveCoupon(@PathVariable Long taskId, Authentication actor) {
        return service.approveCoupon(taskId, actor);
    }

    @PostMapping("/approvals/{taskId}/reject")
    public TicketDtos.TicketView reject(@PathVariable Long taskId,
                                         @Valid @RequestBody ApprovalDtos.DecisionRequest request,
                                         Authentication actor) {
        return service.reject(taskId, request.reason(), actor);
    }

    @PostMapping("/approvals/{taskId}/assign-supervisor")
    public TicketDtos.TicketView assign(@PathVariable Long taskId,
                                         @Valid @RequestBody ApprovalDtos.DecisionRequest request,
                                         Authentication actor) {
        return service.assignSupervisor(taskId, request.reason(), actor);
    }

    @PostMapping("/approvals/{taskId}/review-refund")
    public TicketDtos.TicketView review(@PathVariable Long taskId,
                                         @Valid @RequestBody ApprovalDtos.RefundReviewRequest request,
                                         Authentication actor) {
        return service.reviewRefund(taskId, request, actor);
    }
}
