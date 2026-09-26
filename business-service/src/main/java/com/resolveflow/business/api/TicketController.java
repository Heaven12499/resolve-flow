package com.resolveflow.business.api;

import com.resolveflow.business.service.TicketService;
import jakarta.validation.Valid;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/tickets")
public class TicketController {
    private final TicketService service;
    public TicketController(TicketService service) { this.service = service; }

    @GetMapping
    public TicketDtos.TicketPage list(@RequestParam(defaultValue = "0") int page,
                                      @RequestParam(defaultValue = "20") int size,
                                      @RequestParam(required = false) String status,
                                      @RequestParam(required = false) String keyword) {
        return service.list(page, size, status, keyword);
    }

    @GetMapping("/{id}")
    public TicketDtos.TicketView get(@PathVariable Long id) { return service.get(id); }

    @PostMapping
    public TicketDtos.TicketView create(@Valid @RequestBody TicketDtos.CreateTicketRequest request,
                                         @RequestHeader(name = "Idempotency-Key", required = false) String idempotencyKey,
                                         Authentication authentication) {
        return service.create(request, authentication.getName(), idempotencyKey);
    }

    @PostMapping("/{id}/process")
    public TicketDtos.TicketView retry(@PathVariable Long id, Authentication authentication) {
        return service.retry(id, authentication.getName());
    }

    @PostMapping("/{id}/messages")
    public TicketDtos.TicketView addCustomerMessage(@PathVariable Long id,
                                                     @Valid @RequestBody TicketDtos.AddMessageRequest request,
                                                     Authentication authentication) {
        return service.addCustomerMessage(id, request, authentication.getName());
    }
}
