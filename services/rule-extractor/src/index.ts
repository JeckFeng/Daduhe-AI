import express, { Request, Response } from "express";
import { v4 as uuidv4 } from "uuid";

import { tracingMiddleware } from "./common/tracing";
import { log } from "./common/logging";
import healthRouter from "./common/health";
import { ErrorCode, errorResponse } from "./common/error-codes";

const app = express();
app.use(express.json());

// ============================================================
// 中间件: X-Trace-Id 注入与透传
// ============================================================

app.use(tracingMiddleware);

// ============================================================
// 健康检查
// ============================================================

app.use(healthRouter);

// ============================================================
// API: 触发规则抽取 (接收HT异步通知)
// ============================================================

app.post("/api/v1/rules/extract", (req: Request, res: Response) => {
  const { doc_id } = req.body;
  const traceId = (req.headers["x-trace-id"] as string) || "";

  log.info(traceId, "rule extraction triggered", { doc_id });

  res.status(202).json({
    code: 0,
    message: "accepted",
    data: {
      task_id: `r-task-${uuidv4().slice(0, 8)}`,
      status: "processing",
    },
  });
});

// ============================================================
// API: 查询规则库
// ============================================================

app.get("/api/v1/rules/search", (req: Request, res: Response) => {
  const { keyword, category, doc_id, page = "1", page_size = "20" } = req.query;

  // TODO: 实现规则库查询逻辑
  res.json({
    code: 0,
    data: {
      items: [],
      total: 0,
      page: parseInt(page as string),
      page_size: parseInt(page_size as string),
    },
  });
});

// ============================================================
// Prometheus metrics 端点
// ============================================================

app.get("/metrics", (_req: Request, res: Response) => {
  res.set("Content-Type", "text/plain");
  res.send("# TODO: expose daduh_* metrics\n");
});

// ============================================================
// 启动
// ============================================================

const PORT = parseInt(process.env.PORT || "3000");
app.listen(PORT, () => {
  log.info(`rule-extractor-${uuidv4()}`, `rule-extractor listening on port ${PORT}`);
});
