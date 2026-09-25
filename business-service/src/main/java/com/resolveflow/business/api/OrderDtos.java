package com.resolveflow.business.api;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;

public final class OrderDtos {
    private OrderDtos() {}
    public record LogisticsEventView(Long id, String status, String description, Instant occurredAt) {}
    public record OrderView(Long id, String orderNo, Long customerId, String productName, BigDecimal amount,
                            String status, Instant shippedAt, Instant promisedDeliveryAt, Instant createdAt,
                            List<LogisticsEventView> logisticsEvents) {}
}
