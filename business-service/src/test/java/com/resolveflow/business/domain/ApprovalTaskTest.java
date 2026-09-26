package com.resolveflow.business.domain;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class ApprovalTaskTest {
    @Test
    void terminalDecisionCannotBeAppliedTwice() {
        ApprovalTask task = new ApprovalTask(null, "coupon_compensation", "{\"coupon_amount\":5}");

        task.approve("{\"approved_by\":\"agent\"}");

        assertThat(task.getStatus()).isEqualTo("approved");
        assertThatThrownBy(() -> task.reject("{\"reason\":\"duplicate\"}"))
                .isInstanceOf(IllegalStateException.class)
                .hasMessage("该审批任务已被处理");
    }

    @Test
    void inReviewTaskCanReceiveFinalDecisionOnce() {
        ApprovalTask task = new ApprovalTask(null, "refund_review", "{}");

        task.assign("{\"assigned_to\":\"supervisor\"}");
        task.approve("{\"decision\":\"approve_refund\"}");

        assertThat(task.getStatus()).isEqualTo("approved");
        assertThatThrownBy(() -> task.approve("{}"))
                .isInstanceOf(IllegalStateException.class);
    }
}
