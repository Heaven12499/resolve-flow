package com.resolveflow.business.domain;

import jakarta.persistence.*;
import java.math.BigDecimal;
import java.time.Instant;

@Entity
@Table(name = "business_orders")
public class BusinessOrder {
    @Id @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;
    @Column(name = "order_no", nullable = false, unique = true, length = 64)
    private String orderNo;
    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;
    @Column(name = "product_name", nullable = false, length = 255)
    private String productName;
    @Column(nullable = false, precision = 12, scale = 2)
    private BigDecimal amount;
    @Column(nullable = false, length = 30)
    private String status;
    @Column(name = "shipped_at")
    private Instant shippedAt;
    @Column(name = "promised_delivery_at")
    private Instant promisedDeliveryAt;
    @Version
    private long version;
    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt = Instant.now();

    protected BusinessOrder() {}
    public BusinessOrder(String orderNo, Customer customer, String productName, BigDecimal amount,
                         String status, Instant shippedAt, Instant promisedDeliveryAt) {
        this.orderNo = orderNo; this.customer = customer; this.productName = productName;
        this.amount = amount; this.status = status; this.shippedAt = shippedAt;
        this.promisedDeliveryAt = promisedDeliveryAt;
    }
    public Long getId() { return id; }
    public String getOrderNo() { return orderNo; }
    public Customer getCustomer() { return customer; }
    public String getProductName() { return productName; }
    public BigDecimal getAmount() { return amount; }
    public String getStatus() { return status; }
    public Instant getShippedAt() { return shippedAt; }
    public Instant getPromisedDeliveryAt() { return promisedDeliveryAt; }
    public Instant getCreatedAt() { return createdAt; }
}
