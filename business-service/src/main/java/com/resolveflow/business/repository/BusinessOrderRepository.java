package com.resolveflow.business.repository;

import com.resolveflow.business.domain.BusinessOrder;
import org.springframework.data.jpa.repository.JpaRepository;
import java.util.Optional;

public interface BusinessOrderRepository extends JpaRepository<BusinessOrder, Long> {
    Optional<BusinessOrder> findByOrderNo(String orderNo);
}
