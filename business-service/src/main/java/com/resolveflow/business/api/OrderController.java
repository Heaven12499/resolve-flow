package com.resolveflow.business.api;

import com.resolveflow.business.repository.BusinessOrderRepository;
import com.resolveflow.business.repository.LogisticsEventRepository;
import jakarta.persistence.EntityNotFoundException;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/orders")
public class OrderController {
    private final BusinessOrderRepository orders;
    private final LogisticsEventRepository logistics;
    public OrderController(BusinessOrderRepository orders, LogisticsEventRepository logistics) {
        this.orders = orders; this.logistics = logistics;
    }

    @GetMapping("/{orderNo}")
    public OrderDtos.OrderView get(@PathVariable String orderNo) {
        var order = orders.findByOrderNo(orderNo).orElseThrow(() -> new EntityNotFoundException("订单不存在"));
        var events = logistics.findByOrderIdOrderByOccurredAtAsc(order.getId()).stream()
                .map(item -> new OrderDtos.LogisticsEventView(item.getId(), item.getStatus(), item.getDescription(), item.getOccurredAt()))
                .toList();
        return new OrderDtos.OrderView(order.getId(), order.getOrderNo(), order.getCustomer().getId(),
                order.getProductName(), order.getAmount(), order.getStatus(), order.getShippedAt(),
                order.getPromisedDeliveryAt(), order.getCreatedAt(), events);
    }
}
