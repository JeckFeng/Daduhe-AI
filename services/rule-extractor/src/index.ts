import express, { Request, Response } from "express";
import { v4 as uuidv4 } from "uuid";

const app = express();
app.use(express.json());

// ============================================================
// 中间件: Trace-Id 注入与透传
// ============================================================

app.use((req: Request, _res: Response, next) => {
  const traceId = (req.headers["x-trace-id"] as string) || `rule-extractor-${uuidv4()}`;
  req.headers["x-trace-id"] = traceId;
  next();
});

// ============================================================
// 健康检查
// ============================================================

app.get("/health", (_req: Request, res: Response) => {
  res.json({ status: "ok" });
});

app.get("/ready", (_req: Request, res: Response) => {
  res.json({ status: "ready", checks: { db: "ok" } });
});

// ============================================================
// API: 触发规则抽取 (接收HT异步通知)
// ============================================================

app.post("/api/v1/rules/extract", (req: Request, res: Response) => {
  const { doc_id } = req.body;
  const traceId = req.headers["x-trace-id"];

  console.log(
    JSON.stringify({
      timestamp: new Date().toISOString(),
      level: "INFO",
      service: "rule-extractor",
      trace_id: traceId,
      message: "rule extraction triggered",
      detail: { doc_id },
    })
  );

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
  console.log(
    JSON.stringify({
      timestamp: new Date().toISOString(),
      level: "INFO",
      service: "rule-extractor",
      trace_id: `rule-extractor-${uuidv4()}`,
      message: `rule-extractor listening on port ${PORT}`,
    })
  );
});
