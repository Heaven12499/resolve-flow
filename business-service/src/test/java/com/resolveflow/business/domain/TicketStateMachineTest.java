package com.resolveflow.business.domain;

import org.junit.jupiter.api.Test;
import java.math.BigDecimal;
import java.time.Instant;
import static org.junit.jupiter.api.Assertions.*;

class TicketStateMachineTest {
    private Ticket ticket() {
        var customer = new Customer("test", null);
        var order = new BusinessOrder("O-1", customer, "product", BigDecimal.ONE,
                "shipped", Instant.now(), Instant.now());
        return new Ticket("T-1", customer, order, "title", "content");
    }

    @Test
    void aiRecommendationCannotSkipTheQueueState() {
        var ticket = ticket();
        assertThrows(IllegalStateException.class,
                () -> ticket.applyAiResult("logistics_query", "medium", "low", TicketStatus.RESOLVED));
    }

    @Test
    void queuedTicketCanApplyAControlledAiRecommendation() {
        var ticket = ticket();
        ticket.queueForAi();
        ticket.applyAiResult("refund_risk_review", "high", "high", TicketStatus.HUMAN_REVIEW);
        assertEquals(TicketStatus.HUMAN_REVIEW, ticket.getStatus());
    }

    @Test
    void refundReviewCanRequestEvidenceAndResumeAi() {
        var ticket = ticket();
        ticket.queueForAi();
        ticket.applyAiResult("refund_risk_review", "high", "high", TicketStatus.HUMAN_REVIEW);
        ticket.waitForCustomer();
        ticket.retryAi();
        assertEquals(TicketStatus.AI_QUEUED, ticket.getStatus());
    }

    @Test
    void aiCanPauseAQueuedTicketForCustomerEvidence() {
        var ticket = ticket();
        ticket.queueForAi();

        ticket.applyAiResult("refund_risk_review", "high", "high", TicketStatus.WAITING_CUSTOMER);

        assertEquals(TicketStatus.WAITING_CUSTOMER, ticket.getStatus());
    }

    @Test
    void exhaustedAiFailureEntersHumanReviewQueue() {
        var ticket = ticket();
        ticket.queueForAi();
        ticket.routeAiFailureToHumanReview();
        assertEquals(TicketStatus.HUMAN_REVIEW, ticket.getStatus());
    }
}
