import { Router, Request, Response } from "express";

import { ErrorCode, errorResponse } from "../common/error-codes";
import { log } from "../common/logging";
import { ExtractionTaskService } from "../services/extraction-task";
import { RuleRepository } from "../services/rule-repository";
import { SearchRulesQuery } from "../types/rule";

export function createRulesRouter(
  repository: RuleRepository,
  taskService: ExtractionTaskService
): Router {
  const router = Router();

  router.post("/api/v1/rules/extract", async (req: Request, res: Response) => {
    const { doc_id } = req.body;
    const traceId = getTraceId(req);

    if (!doc_id || typeof doc_id !== "string") {
      res.status(400).json(errorResponse(ErrorCode.MISSING_FIELD, traceId, { field: "doc_id" }));
      return;
    }

    try {
      log.info(traceId, "rule extraction triggered", { doc_id });
      const task = await taskService.enqueue(doc_id, traceId);
      res.status(202).json({
        code: 0,
        message: "accepted",
        data: task,
      });
    } catch (error) {
      const detail = error instanceof Error ? error.message : String(error);
      log.error(traceId, "failed to enqueue rule extraction", { doc_id, error: detail });
      res.status(500).json(errorResponse(ErrorCode.INTERNAL_ERROR, traceId, { detail }));
    }
  });

  router.get("/api/v1/rules/tasks/:task_id", async (req: Request, res: Response) => {
    const traceId = getTraceId(req);
    const task = await repository.findTask(req.params.task_id);

    if (!task) {
      res.status(404).json(errorResponse(ErrorCode.NOT_FOUND, traceId, {
        resource: "extraction task",
        id: req.params.task_id,
      }));
      return;
    }

    res.json({ code: 0, data: task });
  });

  router.get("/api/v1/rules/search", async (req: Request, res: Response) => {
    const traceId = getTraceId(req);
    const parsed = parseSearchQuery(req);

    if ("error" in parsed) {
      res.status(400).json(errorResponse(ErrorCode.INVALID_VALUE, traceId, {
        field: parsed.error.field,
        value: parsed.error.value,
      }));
      return;
    }

    try {
      const result = await repository.searchRules(parsed.query);
      res.json({
        code: 0,
        data: {
          items: result.items,
          total: result.total,
          page: parsed.query.page,
          page_size: parsed.query.page_size,
        },
      });
    } catch (error) {
      const detail = error instanceof Error ? error.message : String(error);
      log.error(traceId, "rule search failed", { error: detail });
      res.status(500).json(errorResponse(ErrorCode.INTERNAL_ERROR, traceId, { detail }));
    }
  });

  return router;
}

function parseSearchQuery(req: Request): { query: SearchRulesQuery } | { error: { field: string; value: string } } {
  const page = parsePositiveInt(req.query.page, 1);
  const pageSize = parsePositiveInt(req.query.page_size, 20);

  if (page === null) return { error: { field: "page", value: String(req.query.page) } };
  if (pageSize === null || pageSize > 100) return { error: { field: "page_size", value: String(req.query.page_size) } };

  return {
    query: {
      keyword: asOptionalString(req.query.keyword),
      category: asOptionalString(req.query.category),
      doc_id: asOptionalString(req.query.doc_id),
      page,
      page_size: pageSize,
    },
  };
}

function parsePositiveInt(value: unknown, defaultValue: number): number | null {
  if (value === undefined) return defaultValue;
  if (typeof value !== "string" || !/^[1-9][0-9]*$/.test(value)) return null;
  return parseInt(value, 10);
}

function asOptionalString(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() ? value.trim() : undefined;
}

function getTraceId(req: Request): string {
  return (req.headers["x-trace-id"] as string) || "";
}
