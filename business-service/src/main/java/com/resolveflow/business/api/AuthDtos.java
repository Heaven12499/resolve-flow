package com.resolveflow.business.api;

import jakarta.validation.constraints.NotBlank;

public final class AuthDtos {
    private AuthDtos() {}
    public record LoginRequest(@NotBlank String username, @NotBlank String password) {}
    public record LoginResponse(String accessToken, String tokenType, long expiresIn, String username, String role) {}
}
