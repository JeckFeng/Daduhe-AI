package com.daduhe.docparser.common;

import jakarta.servlet.*;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.MDC;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

import java.io.IOException;
import java.util.UUID;

/**
 * X-Trace-Id 注入与透传 Filter。
 * 外部请求进入时自动生成 trace_id，调用下游时透传收到的 trace_id。
 */
@Component
@Order(1)
public class TracingFilter implements Filter {

    private static final String TRACE_HEADER = "X-Trace-Id";
    private static final String MDC_KEY = "trace_id";
    private static final String PREFIX = "doc-parser";

    @Override
    public void doFilter(ServletRequest req, ServletResponse resp, FilterChain chain)
            throws IOException, ServletException {

        HttpServletRequest httpReq = (HttpServletRequest) req;
        HttpServletResponse httpResp = (HttpServletResponse) resp;

        String traceId = httpReq.getHeader(TRACE_HEADER);
        if (traceId == null || traceId.isBlank()) {
            traceId = PREFIX + "-" + UUID.randomUUID();
        }

        MDC.put(MDC_KEY, traceId);
        httpResp.setHeader(TRACE_HEADER, traceId);

        try {
            chain.doFilter(req, resp);
        } finally {
            MDC.remove(MDC_KEY);
        }
    }
}
