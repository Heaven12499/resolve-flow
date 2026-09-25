package com.resolveflow.business.api;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import java.time.Instant;
import java.util.Map;

public final class ApprovalDtos {
    private ApprovalDtos() {}
    public record DecisionRequest(@Size(max = 300) String reason) {}
    public record RefundReviewRequest(
            @NotBlank @Pattern(regexp = "request_evidence|approve_refund|reject") String decision,
            @NotBlank @Size(min = 2, max = 300) String reason) {}
    public record ApprovalQueueView(Long id, String taskType, String status, Map<String, Object> proposedData,
                                    Map<String, Object> decisionData, Instant createdAt, Instant decidedAt,
                                    Long ticketId, String ticketNo, String ticketTitle, String ticketContent,
                                    String ticketStatus, String riskLevel) {}
}
