package com.resolveflow.business.api;

import com.resolveflow.business.service.TicketService;
import jakarta.validation.Valid;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.*;
import java.util.List;

@RestController
@RequestMapping("/api/tickets")
public class TicketController {
    private final TicketService service;
    public TicketController(TicketService service) { this.service = service; }

    @GetMapping
    public List<TicketDtos.TicketView> list() { return service.list(); }

    @GetMapping("/{id}")
    public TicketDtos.TicketView get(@PathVariable Long id) { return service.get(id); }

    @PostMapping
    public TicketDtos.TicketView create(@Valid @RequestBody TicketDtos.CreateTicketRequest request,
                                         Authentication authentication) {
        return service.create(request, authentication.getName());
    }

    @PostMapping("/{id}/process")
    public TicketDtos.TicketView retry(@PathVariable Long id, Authentication authentication) {
        return service.retry(id, authentication.getName());
    }
}
