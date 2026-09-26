package com.resolveflow.business.action;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class LocalBusinessActionGatewayTest {
    private final LocalBusinessActionGateway gateway = new LocalBusinessActionGateway();

    @Test
    void couponProviderIsDeterministicForTheSameIdempotencyKey() {
        var first = gateway.issueCoupon("approval:42:issue_coupon", 5, "customer-1");
        var repeated = gateway.issueCoupon("approval:42:issue_coupon", 5, "customer-1");

        assertThat(repeated.externalReference()).isEqualTo(first.externalReference());
        assertThat(first.provider()).isEqualTo("local-demo");
    }
}
