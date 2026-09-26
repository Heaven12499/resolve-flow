package com.resolveflow.business;

import com.resolveflow.business.domain.TicketStatus;
import com.resolveflow.business.repository.ApprovalTaskRepository;
import com.resolveflow.business.repository.TicketRepository;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.domain.PageRequest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.transaction.annotation.Transactional;
import org.testcontainers.containers.MySQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.assertj.core.api.Assertions.assertThat;

@Testcontainers(disabledWithoutDocker = true)
@SpringBootTest(properties = {
        "resolveflow.seed.enabled=true",
        "resolveflow.ai.dispatch.redis-coordination-enabled=false"
})
class MySqlMigrationIntegrationTest {
    @Container
    static final MySQLContainer<?> MYSQL = new MySQLContainer<>("mysql:8.4")
            .withDatabaseName("resolveflow_business")
            .withUsername("resolve_flow")
            .withPassword("resolve_flow");

    @DynamicPropertySource
    static void mysqlProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", MYSQL::getJdbcUrl);
        registry.add("spring.datasource.username", MYSQL::getUsername);
        registry.add("spring.datasource.password", MYSQL::getPassword);
        registry.add("spring.jpa.hibernate.ddl-auto", () -> "validate");
        registry.add("spring.flyway.enabled", () -> "true");
    }

    @Autowired JdbcTemplate jdbc;
    @Autowired TicketRepository tickets;
    @Autowired ApprovalTaskRepository approvals;

    @Test
    void flywaySchemaIsValidForMySqlAndSeedTicketCanBePaged() {
        Integer versionColumns = jdbc.queryForObject("""
                SELECT COUNT(*) FROM information_schema.columns
                WHERE table_schema = DATABASE()
                  AND table_name = 'approval_tasks'
                  AND column_name = 'version'
                """, Integer.class);

        var page = tickets.search(null, "物流", PageRequest.of(0, 10));

        assertThat(versionColumns).isEqualTo(1);
        assertThat(page.getTotalElements()).isEqualTo(1);
        assertThat(page.getContent().getFirst().getStatus()).isEqualTo(TicketStatus.NEW);
    }

    @Test
    @Transactional
    void approvalRepositorySupportsWriteLockLookup() {
        assertThat(approvals.findByIdForUpdate(Long.MAX_VALUE)).isEmpty();
    }
}
