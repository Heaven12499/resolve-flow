package com.resolveflow.business.action;

public interface BusinessActionGateway {
    CouponResult issueCoupon(String idempotencyKey, int amount, String recipientReference);

    record CouponResult(String externalReference, String provider, String status) {}
}
