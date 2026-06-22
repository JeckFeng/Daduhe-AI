import { Router, Request, Response } from "express";

import { checkDb } from "../db/pool";

const router = Router();

/**
 * 健康检查端点:
 *   GET /health → K8s liveness probe
 *   GET /ready  → K8s readiness probe
 */
router.get("/health", (_req: Request, res: Response) => {
  res.json({ status: "ok" });
});

router.get("/ready", async (_req: Request, res: Response) => {
  const dbReady = await checkDb();
  res.status(dbReady ? 200 : 503).json({
    status: dbReady ? "ready" : "not_ready",
    checks: { db: dbReady ? "ok" : "error" },
  });
});

export default router;
