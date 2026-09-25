package com.resolveflow.business.ai;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.dao.DataAccessException;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.DefaultRedisScript;
import org.springframework.stereotype.Component;
import java.time.Duration;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

@Component
public class AiDispatchCoordinator {
    private static final Logger log = LoggerFactory.getLogger(AiDispatchCoordinator.class);
    private static final String LOCK_KEY = "resolveflow:ai:dispatcher";
    private static final DefaultRedisScript<Long> RELEASE_SCRIPT = new DefaultRedisScript<>(
            "if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) else return 0 end",
            Long.class);

    private final StringRedisTemplate redis;
    private final boolean enabled;
    private final Duration ttl;

    public AiDispatchCoordinator(
            StringRedisTemplate redis,
            @Value("${resolveflow.ai.dispatch.redis-coordination-enabled:false}") boolean enabled,
            @Value("${resolveflow.ai.dispatch.lock-ttl:10s}") Duration ttl) {
        this.redis = redis; this.enabled = enabled; this.ttl = ttl;
    }

    public Optional<Lease> tryAcquire() {
        if (!enabled) return Optional.of(new Lease(null, false));
        String token = UUID.randomUUID().toString();
        try {
            Boolean acquired = redis.opsForValue().setIfAbsent(LOCK_KEY, token, ttl);
            return Boolean.TRUE.equals(acquired)
                    ? Optional.of(new Lease(token, true))
                    : Optional.empty();
        } catch (DataAccessException exception) {
            log.warn("Redis dispatcher coordination unavailable; falling back to database locking");
            return Optional.of(new Lease(null, false));
        }
    }

    public final class Lease implements AutoCloseable {
        private final String token;
        private final boolean redisBacked;
        private Lease(String token, boolean redisBacked) {
            this.token = token; this.redisBacked = redisBacked;
        }
        @Override
        public void close() {
            if (!redisBacked) return;
            try {
                redis.execute(RELEASE_SCRIPT, List.of(LOCK_KEY), token);
            } catch (DataAccessException exception) {
                log.warn("Redis dispatcher lease release failed; TTL will release it automatically");
            }
        }
    }
}
