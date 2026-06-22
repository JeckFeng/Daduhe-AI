import { Request, Response, NextFunction } from "express";
import { v4 as uuidv4 } from "uuid";

const TRACE_HEADER = "X-Trace-Id";
const PREFIX = "rule-extractor";

/**
 * X-Trace-Id 注入与透传中间件。
 * 外部请求进入时自动生成，调用下游时透传收到的 trace_id。
 */
export function tracingMiddleware(
  req: Request,
  res: Response,
  next: NextFunction
): void {
  const traceId = (req.headers[TRACE_HEADER.toLowerCase()] as string) || `${PREFIX}-${uuidv4()}`;
  req.headers[TRACE_HEADER.toLowerCase()] = traceId;
  res.setHeader(TRACE_HEADER, traceId);
  next();
}
