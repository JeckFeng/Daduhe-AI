/**
 * 统一错误码体系。业务错误码 = 段号 × 1000 + 序号。
 */
export const ErrorCode = {
  OK: 0,
  MISSING_FIELD: 1001,
  INVALID_VALUE: 1002,
  NOT_FOUND: 3001,
  UPSTREAM_UNAVAILABLE: 4001,
  UPSTREAM_TIMEOUT: 4002,
  RULE_EXTRACTION_FAILED: 5002,
  INTERNAL_ERROR: 9001,
} as const;

const MESSAGES: Record<number, string> = {
  0: "ok",
  1001: "missing required field: {field}",
  1002: "invalid value for {field}: {value}",
  3001: "{resource} not found: {id}",
  4001: "upstream service unavailable: {service}",
  4002: "upstream timeout: {service}",
  5002: "rule extraction failed: {reason}",
  9001: "internal error: {detail}",
};

export interface ErrorResponse {
  code: number;
  message: string;
  trace_id?: string;
}

export function errorResponse(code: number, traceId?: string, args?: Record<string, string>): ErrorResponse {
  let template = MESSAGES[code] || "unknown error";
  if (args) {
    for (const [key, value] of Object.entries(args)) {
      template = template.replace(`{${key}}`, value);
    }
  }
  const resp: ErrorResponse = { code, message: template };
  if (traceId) resp.trace_id = traceId;
  return resp;
}
