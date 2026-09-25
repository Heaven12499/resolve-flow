package com.resolveflow.business.config;

import com.resolveflow.business.domain.*;
import com.resolveflow.business.repository.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;
import java.math.BigDecimal;
import java.time.Instant;
import java.time.temporal.ChronoUnit;

@Component
public class DemoDataSeeder implements ApplicationRunner {
    private final UserAccountRepository users;
    private final CustomerRepository customers;
    private final BusinessOrderRepository orders;
    private final LogisticsEventRepository logistics;
    private final TicketRepository tickets;
    private final TicketMessageRepository messages;
    private final PasswordEncoder encoder;
    private final boolean enabled;
    private final String adminPassword;
    private final String supervisorPassword;
    private final String agentPassword;

    public DemoDataSeeder(UserAccountRepository users, CustomerRepository customers,
                          BusinessOrderRepository orders, LogisticsEventRepository logistics,
                          TicketRepository tickets, TicketMessageRepository messages,
                          PasswordEncoder encoder,
                          @Value("${resolveflow.seed.enabled}") boolean enabled,
                          @Value("${resolveflow.seed.admin-password}") String adminPassword,
                          @Value("${resolveflow.seed.supervisor-password}") String supervisorPassword,
                          @Value("${resolveflow.seed.agent-password}") String agentPassword) {
        this.users = users; this.customers = customers; this.orders = orders; this.logistics = logistics;
        this.tickets = tickets; this.messages = messages;
        this.encoder = encoder; this.enabled = enabled; this.adminPassword = adminPassword;
        this.supervisorPassword = supervisorPassword; this.agentPassword = agentPassword;
    }

    @Override
    @Transactional
    public void run(ApplicationArguments args) {
        if (!enabled) return;
        seedUser("admin", adminPassword, Role.ADMIN);
        seedUser("supervisor", supervisorPassword, Role.SUPERVISOR);
        seedUser("agent", agentPassword, Role.AGENT);
        BusinessOrder order = orders.findByOrderNo("RF202608290001").orElseGet(() -> seedOrder());
        if (tickets.findByTicketNo("TK202608290001").isEmpty()) {
            Ticket ticket = tickets.save(new Ticket(
                    "TK202608290001", order.getCustomer(), order,
                    "物流长时间未更新", "订单已超过承诺送达时间，物流两天没有更新，请帮我查询并处理。"));
            messages.save(new TicketMessage(ticket, "customer", ticket.getContent()));
        }
    }

    private BusinessOrder seedOrder() {
        Customer customer = customers.save(new Customer("演示客户", "138****0001"));
        Instant now = Instant.now();
        BusinessOrder order = orders.save(new BusinessOrder(
                "RF202608290001", customer, "智能降噪耳机", new BigDecimal("299.00"),
                "shipped", now.minus(120, ChronoUnit.HOURS), now.minus(48, ChronoUnit.HOURS)));
        logistics.save(new LogisticsEvent(order, "collected", "快件已揽收", now.minus(116, ChronoUnit.HOURS)));
        logistics.save(new LogisticsEvent(order, "in_transit", "包裹到达中转中心", now.minus(96, ChronoUnit.HOURS)));
        return order;
    }

    private void seedUser(String username, String password, Role role) {
        if (users.findByUsername(username).isEmpty()) {
            users.save(new UserAccount(username, encoder.encode(password), role));
        }
    }
}
