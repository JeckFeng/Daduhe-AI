package com.daduhe.docparser.common;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;

/**
 * 统一 JSON 结构化日志。必含字段: timestamp, level, service, trace_id, message。
 */
public final class StructuredLogger {

    private static final String SERVICE = "doc-parser";
    private static final ObjectMapper MAPPER = new ObjectMapper();

    private final Logger logger;

    private StructuredLogger(Class<?> clazz) {
        this.logger = LoggerFactory.getLogger(clazz);
    }

    public static StructuredLogger of(Class<?> clazz) {
        return new StructuredLogger(clazz);
    }

    public void info(String traceId, String message, Map<String, Object> detail) {
        log("INFO", traceId, message, detail);
    }

    public void warn(String traceId, String message, Map<String, Object> detail) {
        log("WARN", traceId, message, detail);
    }

    public void error(String traceId, String message, Map<String, Object> detail) {
        log("ERROR", traceId, message, detail);
    }

    public void debug(String traceId, String message, Map<String, Object> detail) {
        log("DEBUG", traceId, message, detail);
    }

    private void log(String level, String traceId, String message, Map<String, Object> detail) {
        Map<String, Object> entry = new LinkedHashMap<>();
        entry.put("timestamp", Instant.now().toString());
        entry.put("level", level);
        entry.put("service", SERVICE);
        entry.put("trace_id", traceId != null ? traceId : "");
        entry.put("message", message);
        if (detail != null && !detail.isEmpty()) {
            entry.put("detail", detail);
        }
        try {
            String json = MAPPER.writeValueAsString(entry);
            switch (level) {
                case "ERROR" -> logger.error(json);
                case "WARN"  -> logger.warn(json);
                case "DEBUG" -> logger.debug(json);
                default      -> logger.info(json);
            }
        } catch (JsonProcessingException e) {
            logger.error("Failed to serialize log entry", e);
        }
    }
}
