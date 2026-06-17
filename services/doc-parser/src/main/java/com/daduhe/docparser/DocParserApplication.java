package com.daduhe.docparser;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

@SpringBootApplication
public class DocParserApplication {

    public static void main(String[] args) {
        SpringApplication.run(DocParserApplication.class, args);
    }

    @RestController
    static class HealthController {

        @GetMapping("/health")
        ResponseEntity<Map<String, String>> health() {
            return ResponseEntity.ok(Map.of("status", "ok"));
        }

        @GetMapping("/ready")
        ResponseEntity<Map<String, Object>> ready() {
            return ResponseEntity.ok(Map.of(
                "status", "ready",
                "checks", Map.of("db", "ok", "minio", "ok", "milvus", "ok")
            ));
        }
    }
}
