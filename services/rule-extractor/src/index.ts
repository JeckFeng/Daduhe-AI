import express, { Request, Response } from "express";
import { v4 as uuidv4 } from "uuid";

import { tracingMiddleware } from "./common/tracing";
import { log } from "./common/logging";
import healthRouter from "./common/health";
import { errorDetail } from "./common/error-detail";
import { env } from "./config/env";
import { pool } from "./db/pool";
import { runMigrations } from "./db/migrations";
import { createRulesRouter } from "./routes/rules";
import { RuleRepository } from "./services/rule-repository";
import { ExtractionTaskService } from "./services/extraction-task";

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

const repository = new RuleRepository(pool);
const taskService = new ExtractionTaskService(repository);
app.use(createRulesRouter(repository, taskService));

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

async function start(): Promise<void> {
  const traceId = `rule-extractor-${uuidv4()}`;
  await runMigrations(pool);
  app.listen(env.port, () => {
    log.info(traceId, `rule-extractor listening on port ${env.port}`);
  });
}

start().catch((error) => {
  log.error(`rule-extractor-${uuidv4()}`, "rule-extractor failed to start", errorDetail(error));
  process.exit(1);
});
