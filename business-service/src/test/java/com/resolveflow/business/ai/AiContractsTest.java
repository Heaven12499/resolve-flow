package com.resolveflow.business.ai;

import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.databind.json.JsonMapper;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class AiContractsTest {
    @Test
    void deserializesMultiAgentTraceFromPythonSnakeCaseContract() throws Exception {
        var mapper = JsonMapper.builder()
                .addModule(new JavaTimeModule())
                .propertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE)
                .build();
        String payload = """
                {
                  "task_id":"AIT-1","ticket_id":7,"business_version":2,"status":"SUCCEEDED",
                  "intent":"refund_risk_review","priority":"high","risk_level":"high",
                  "recommended_action":"ESCALATE_REFUND_REVIEW","suggested_coupon_amount":null,
                  "reply_draft":"转主管复核","confidence":0.9,"requires_human_approval":true,
                  "evidence":[],"model_source":"rules","fallback_reason":null,
                  "orchestration_plan":{"route":"refund_agent_investigation"},
                  "execution_trace":[{
                    "sequence":1,"agent_name":"supervisor","status":"completed",
                    "provider":"rules","model":null,"input_data":{"content_length":8},
                    "output_data":{"route":"refund_agent_investigation"},"error":null,
                    "duration_ms":3,"started_at":"2026-09-26T05:00:00Z",
                    "finished_at":"2026-09-26T05:00:00.003Z"
                  }],
                  "knowledge_sources":[],"review_package":{"recommended_next_step":"supervisor_review"}
                }
                """;

        var result = mapper.readValue(payload, AiContracts.AnalyzeResult.class);

        assertEquals("refund_agent_investigation", result.orchestrationPlan().get("route"));
        assertEquals("supervisor", result.executionTrace().getFirst().agentName());
        assertEquals(3, result.executionTrace().getFirst().durationMs());
        assertEquals("supervisor_review", result.reviewPackage().get("recommended_next_step"));
    }
}
