package com.resolveflow.business;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableAsync;

@EnableAsync
@SpringBootApplication
public class ResolveFlowBusinessApplication {
    public static void main(String[] args) {
        SpringApplication.run(ResolveFlowBusinessApplication.class, args);
    }
}
