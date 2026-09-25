package com.resolveflow.business.repository;

import com.resolveflow.business.domain.Ticket;
import org.springframework.data.jpa.repository.JpaRepository;
import java.util.List;
import java.util.Optional;

public interface TicketRepository extends JpaRepository<Ticket, Long> {
    List<Ticket> findAllByOrderByCreatedAtDesc();
    Optional<Ticket> findByTicketNo(String ticketNo);
}
