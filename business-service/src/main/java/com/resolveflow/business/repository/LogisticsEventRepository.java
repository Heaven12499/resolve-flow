package com.resolveflow.business.repository;

import com.resolveflow.business.domain.LogisticsEvent;
import org.springframework.data.jpa.repository.JpaRepository;
import java.util.List;

public interface LogisticsEventRepository extends JpaRepository<LogisticsEvent, Long> {
    List<LogisticsEvent> findByOrderIdOrderByOccurredAtAsc(Long orderId);
}
