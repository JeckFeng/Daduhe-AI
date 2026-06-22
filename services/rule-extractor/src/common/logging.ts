const SERVICE = "rule-extractor";

type LogLevel = "ERROR" | "WARN" | "INFO" | "DEBUG";

interface LogEntry {
  timestamp: string;
  level: LogLevel;
  service: string;
  trace_id: string;
  message: string;
  detail?: Record<string, unknown>;
}

function write(level: LogLevel, traceId: string, message: string, detail?: Record<string, unknown>): void {
  const entry: LogEntry = {
    timestamp: new Date().toISOString(),
    level,
    service: SERVICE,
    trace_id: traceId,
    message,
  };
  if (detail && Object.keys(detail).length > 0) {
    entry.detail = detail;
  }
  process.stderr.write(JSON.stringify(entry) + "\n");
}

export const log = {
  info: (traceId: string, message: string, detail?: Record<string, unknown>) =>
    write("INFO", traceId, message, detail),
  warn: (traceId: string, message: string, detail?: Record<string, unknown>) =>
    write("WARN", traceId, message, detail),
  error: (traceId: string, message: string, detail?: Record<string, unknown>) =>
    write("ERROR", traceId, message, detail),
  debug: (traceId: string, message: string, detail?: Record<string, unknown>) =>
    write("DEBUG", traceId, message, detail),
};
