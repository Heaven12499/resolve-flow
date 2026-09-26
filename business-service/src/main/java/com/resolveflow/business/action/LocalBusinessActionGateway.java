package com.resolveflow.business.action;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;
import java.nio.charset.StandardCharsets;
import java.util.UUID;

@Component
@ConditionalOnProperty(name = "resolveflow.business-actions.provider", havingValue = "local", matchIfMissing = true)
public class LocalBusinessActionGateway implements BusinessActionGateway {
    @Override
    public CouponResult issueCoupon(String idempotencyKey, int amount, String recipientReference) {
        String suffix = UUID.nameUUIDFromBytes(idempotencyKey.getBytes(StandardCharsets.UTF_8))
                .toString().replace("-", "").substring(0, 8).toUpperCase();
        return new CouponResult("RF" + amount + "-" + suffix, "local-demo", "issued");
    }
}
