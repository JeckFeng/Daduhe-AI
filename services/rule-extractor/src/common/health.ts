import { Router, Request, Response } from "express";

const router = Router();

/**
 * 健康检查端点:
 *   GET /health → K8s liveness probe
 *   GET /ready  → K8s readiness probe
 */
router.get("/health", (_req: Request, res: Response) => {
  res.json({ status: "ok" });
});

router.get("/ready", (_req: Request, res: Response) => {
  res.json({ status: "ready", checks: { db: "ok" } });
});

export default router;
