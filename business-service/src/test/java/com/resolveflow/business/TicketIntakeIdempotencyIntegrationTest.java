package com.resolveflow.business;

import com.resolveflow.business.api.TicketDtos;
import com.resolveflow.business.repository.TicketRepository;
import com.resolveflow.business.service.TicketService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.transaction.annotation.Transactional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@SpringBootTest(properties = {
        "spring.datasource.url=jdbc:h2:mem:resolveflow-idempotency;MODE=MySQL;DB_CLOSE_DELAY=-1",
        "spring.datasource.driver-class-name=org.h2.Driver",
        "spring.datasource.username=sa",
        "spring.datasource.password=",
        "spring.jpa.hibernate.ddl-auto=create-drop",
        "spring.flyway.enabled=false",
        "resolveflow.seed.enabled=true",
        "resolveflow.ai.dispatch.redis-coordination-enabled=false"
})
@Transactional
class TicketIntakeIdempotencyIntegrationTest {
    @Autowired TicketService service;
    @Autowired TicketRepository tickets;

    @Test
    void repeatedRequestWithSameKeyReturnsOriginalTicket() {
        long before = tickets.count();
        var request = new TicketDtos.CreateTicketRequest(
                "RF202608290001", "同一个上游请求即使重试也只能创建一张工单", "幂等接入测试");

        var first = service.create(request, "admin", "intake-test-001");
        var repeated = service.create(request, "admin", "intake-test-001");

        assertThat(repeated.id()).isEqualTo(first.id());
        assertThat(tickets.count()).isEqualTo(before + 1);
    }

    @Test
    void reusingKeyForDifferentPayloadIsRejected() {
        service.create(new TicketDtos.CreateTicketRequest(
                "RF202608290001", "第一次提交的工单内容", "第一次请求"), "admin", "intake-test-002");

        assertThatThrownBy(() -> service.create(new TicketDtos.CreateTicketRequest(
                "RF202608290001", "被错误复用幂等键的另一份内容", "第二次请求"),
                "admin", "intake-test-002"))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("同一幂等键");
    }
}
