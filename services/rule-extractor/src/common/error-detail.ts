export function errorDetail(error: unknown): Record<string, unknown> {
  if (!(error instanceof Error)) {
    return { error: String(error) };
  }

  const detail: Record<string, unknown> = {
    name: error.name,
    message: error.message,
  };

  const maybeNodeError = error as NodeJS.ErrnoException & {
    address?: string;
    port?: number;
  };
  if (maybeNodeError.code) detail.code = maybeNodeError.code;
  if (maybeNodeError.address) detail.address = maybeNodeError.address;
  if (maybeNodeError.port) detail.port = maybeNodeError.port;
  if (error.stack) detail.stack = error.stack;

  if (error instanceof AggregateError) {
    detail.errors = error.errors.map((inner) => errorDetail(inner));
  }

  return detail;
}
