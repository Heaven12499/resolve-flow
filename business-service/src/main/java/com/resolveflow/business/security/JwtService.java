package com.resolveflow.business.security;

import com.auth0.jwt.JWT;
import com.auth0.jwt.algorithms.Algorithm;
import com.auth0.jwt.interfaces.DecodedJWT;
import com.resolveflow.business.domain.UserAccount;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.Date;

@Service
public class JwtService {
    private final Algorithm algorithm;
    private final long ttlMinutes;

    public JwtService(@Value("${resolveflow.security.jwt-secret}") String secret,
                      @Value("${resolveflow.security.token-ttl-minutes}") long ttlMinutes) {
        if (secret.length() < 32) throw new IllegalArgumentException("JWT secret must be at least 32 characters");
        this.algorithm = Algorithm.HMAC256(secret);
        this.ttlMinutes = ttlMinutes;
    }

    public String issue(UserAccount user) {
        Instant now = Instant.now();
        return JWT.create()
                .withIssuer("resolveflow-business")
                .withSubject(user.getUsername())
                .withClaim("role", user.getRole().name())
                .withIssuedAt(Date.from(now))
                .withExpiresAt(Date.from(now.plus(ttlMinutes, ChronoUnit.MINUTES)))
                .sign(algorithm);
    }

    public DecodedJWT verify(String token) {
        return JWT.require(algorithm).withIssuer("resolveflow-business").build().verify(token);
    }

    public long ttlSeconds() { return ttlMinutes * 60; }
}
