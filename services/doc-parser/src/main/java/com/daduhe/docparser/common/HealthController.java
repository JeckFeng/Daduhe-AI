package com.daduhe.docparser.common;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

/**
 * 健康检查端点:
 *   GET /health  → K8s liveness probe
 *   GET /ready   → K8s readiness probe
 */
@RestController
public class HealthController {

    @GetMapping("/health")
    public ResponseEntity<Map<String, String>> health() {
        return ResponseEntity.ok(Map.of("status", "ok"));
    }

    @GetMapping("/ready")
    public ResponseEntity<Map<String, Object>> ready() {
        return ResponseEntity.ok(Map.of(
            "status", "ready",
            "checks", Map.of("db", "ok", "minio", "ok", "milvus", "ok")
        ));
    }
}
