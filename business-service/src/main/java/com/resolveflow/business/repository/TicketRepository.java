package com.resolveflow.business.repository;

import com.resolveflow.business.domain.Ticket;
import com.resolveflow.business.domain.TicketStatus;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.EntityGraph;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import java.util.Optional;

public interface TicketRepository extends JpaRepository<Ticket, Long> {
    Optional<Ticket> findByTicketNo(String ticketNo);

    @EntityGraph(attributePaths = {"customer", "order"})
    @Query("select ticket from Ticket ticket where "
            + "(:status is null or ticket.status = :status) and "
            + "(:keyword is null or lower(ticket.ticketNo) like lower(concat('%', :keyword, '%')) "
            + "or lower(ticket.title) like lower(concat('%', :keyword, '%')))")
    Page<Ticket> search(@Param("status") TicketStatus status,
                        @Param("keyword") String keyword,
                        Pageable pageable);
}
