package com.resolveflow.business.config;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.web.client.RestClientCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.client.RestClient;
import java.time.Duration;
import org.slf4j.MDC;
import com.resolveflow.business.web.RequestIdFilter;

@Configuration
public class AiClientConfig {
    @Bean
    RestClient aiRestClient(
            RestClient.Builder builder,
            @Value("${resolveflow.ai.base-url}") String baseUrl,
            @Value("${resolveflow.ai.internal-token}") String internalToken,
            @Value("${resolveflow.ai.connect-timeout}") Duration connectTimeout,
            @Value("${resolveflow.ai.read-timeout}") Duration readTimeout) {
        if (internalToken == null || internalToken.length() < 32) {
            throw new IllegalStateException("INTERNAL_API_TOKEN must contain at least 32 characters");
        }
        var requestFactory = new SimpleClientHttpRequestFactory();
        requestFactory.setConnectTimeout(connectTimeout);
        requestFactory.setReadTimeout(readTimeout);
        return builder.baseUrl(baseUrl)
                .requestFactory(requestFactory)
                .defaultHeader("X-Internal-Token", internalToken)
                .requestInterceptor((request, body, execution) -> {
                    String requestId = MDC.get(RequestIdFilter.MDC_KEY);
                    if (requestId != null) request.getHeaders().set(RequestIdFilter.HEADER, requestId);
                    return execution.execute(request, body);
                })
                .build();
    }
}
