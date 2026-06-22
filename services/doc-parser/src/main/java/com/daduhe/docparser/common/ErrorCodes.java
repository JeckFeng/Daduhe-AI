package com.daduhe.docparser.common;

import java.util.LinkedHashMap;
import java.util.Map;

/**
 * 统一错误码体系。业务错误码 = 段号 × 1000 + 序号。
 */
public final class ErrorCodes {

    private ErrorCodes() {}

    public static final int OK                   = 0;
    public static final int MISSING_FIELD        = 1001;
    public static final int INVALID_VALUE        = 1002;
    public static final int NOT_FOUND            = 3001;
    public static final int UPSTREAM_UNAVAILABLE = 4001;
    public static final int UPSTREAM_TIMEOUT     = 4002;
    public static final int DOC_PROCESSING_FAILED = 5001;
    public static final int INTERNAL_ERROR       = 9001;

    private static final Map<Integer, String> MESSAGES = Map.ofEntries(
        Map.entry(0,    "ok"),
        Map.entry(1001, "missing required field: {field}"),
        Map.entry(1002, "invalid value for {field}: {value}"),
        Map.entry(3001, "{resource} not found: {id}"),
        Map.entry(4001, "upstream service unavailable: {service}"),
        Map.entry(4002, "upstream timeout: {service}"),
        Map.entry(5001, "document processing failed: {reason}"),
        Map.entry(9001, "internal error: {detail}")
    );

    public static Map<String, Object> body(int code, String traceId) {
        return body(code, traceId, Map.of());
    }

    /**
     * 构建统一错误响应体: { code, message, trace_id }。
     * message 模板中的占位符用 args 填充。
     */
    public static Map<String, Object> body(int code, String traceId, Map<String, String> args) {
        String template = MESSAGES.getOrDefault(code, "unknown error");
        String message = template;
        for (var entry : args.entrySet()) {
            message = message.replace("{" + entry.getKey() + "}", entry.getValue());
        }
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("code", code);
        body.put("message", message);
        if (traceId != null) {
            body.put("trace_id", traceId);
        }
        return body;
    }
}
