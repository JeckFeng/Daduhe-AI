import { env } from "../config/env";
import { Chunk, ChunkListResponse } from "../types/chunk";

const PAGE_SIZE = 50;
const TIMEOUT_MS = 15_000;

export class UpstreamError extends Error {
  constructor(message: string, public readonly status?: number) {
    super(message);
  }
}

export async function fetchChunksByDocId(docId: string, traceId: string): Promise<Chunk[]> {
  const chunks: Chunk[] = [];
  let page = 1;
  let total = 0;

  do {
    const url = new URL("/api/v1/chunks", env.docParserUrl);
    url.searchParams.set("doc_id", docId);
    url.searchParams.set("page", String(page));
    url.searchParams.set("page_size", String(PAGE_SIZE));

    const response = await fetchWithTimeout(url, traceId);
    const body = (await response.json()) as ChunkListResponse;

    if (!response.ok || body.code !== 0 || !body.data) {
      throw new UpstreamError(body.message || `doc-parser returned ${response.status}`, response.status);
    }

    chunks.push(...body.data.items);
    total = body.data.total;
    page += 1;
  } while (chunks.length < total);

  return chunks;
}

async function fetchWithTimeout(url: URL, traceId: string): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);

  try {
    return await fetch(url, {
      method: "GET",
      headers: {
        "X-Trace-Id": traceId,
      },
      signal: controller.signal,
    });
  } catch (error) {
    if (error instanceof Error && error.name === "AbortError") {
      throw new UpstreamError("doc-parser request timeout");
    }
    throw error;
  } finally {
    clearTimeout(timer);
  }
}
