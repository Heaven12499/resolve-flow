package com.resolveflow.business;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.web.servlet.MockMvc;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@AutoConfigureMockMvc
@SpringBootTest(properties = {
        "spring.datasource.url=jdbc:h2:mem:resolveflow;MODE=MySQL;DB_CLOSE_DELAY=-1",
        "spring.datasource.driver-class-name=org.h2.Driver",
        "spring.datasource.username=sa",
        "spring.datasource.password=",
        "spring.jpa.hibernate.ddl-auto=create-drop",
        "spring.flyway.enabled=false",
        "resolveflow.seed.enabled=false"
})
class ApplicationContextTest {
    @Autowired MockMvc mvc;

    @Test
    void contextLoadsWithSeparatedBusinessSchema() {}

    @Test
    void healthPropagatesRequestIdAndPrometheusIsScrapeable() throws Exception {
        mvc.perform(get("/api/health").header("X-Request-Id", "integration-request-123"))
                .andExpect(status().isOk())
                .andExpect(header().string("X-Request-Id", "integration-request-123"));
        mvc.perform(get("/actuator/prometheus"))
                .andExpect(status().isOk())
                .andExpect(content().string(org.hamcrest.Matchers.containsString(
                        "resolveflow_ai_tasks_claimed_total")));
    }
}
