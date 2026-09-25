package com.resolveflow.business.api;

import com.resolveflow.business.repository.UserAccountRepository;
import com.resolveflow.business.security.JwtService;
import jakarta.validation.Valid;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/auth")
public class AuthController {
    private final AuthenticationManager authenticationManager;
    private final UserAccountRepository users;
    private final JwtService jwtService;
    public AuthController(AuthenticationManager authenticationManager, UserAccountRepository users, JwtService jwtService) {
        this.authenticationManager = authenticationManager; this.users = users; this.jwtService = jwtService;
    }

    @PostMapping("/login")
    public AuthDtos.LoginResponse login(@Valid @RequestBody AuthDtos.LoginRequest request) {
        authenticationManager.authenticate(new UsernamePasswordAuthenticationToken(request.username(), request.password()));
        var user = users.findByUsername(request.username()).orElseThrow();
        return new AuthDtos.LoginResponse(jwtService.issue(user), "bearer", jwtService.ttlSeconds(),
                user.getUsername(), user.getRole().name().toLowerCase());
    }
}
