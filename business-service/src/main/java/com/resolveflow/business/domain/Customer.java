package com.resolveflow.business.domain;

import jakarta.persistence.*;
import java.time.Instant;

@Entity
@Table(name = "customers")
public class Customer {
    @Id @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;
    @Column(nullable = false, length = 100)
    private String name;
    @Column(length = 30)
    private String phone;
    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt = Instant.now();

    protected Customer() {}
    public Customer(String name, String phone) { this.name = name; this.phone = phone; }
    public Long getId() { return id; }
    public String getName() { return name; }
    public String getPhone() { return phone; }
}
