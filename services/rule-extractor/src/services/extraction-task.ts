import { v4 as uuidv4 } from "uuid";

import { log } from "../common/logging";
import { errorDetail } from "../common/error-detail";
import { fetchChunksByDocId } from "./doc-parser-client";
import { extractRulesFromChunks } from "./rule-extractor";
import { RuleRepository } from "./rule-repository";

export class ExtractionTaskService {
  constructor(private readonly repository: RuleRepository) {}

  async enqueue(docId: string, traceId: string): Promise<{ task_id: string; status: "processing" }> {
    const taskId = `r-task-${uuidv4().slice(0, 8)}`;
    await this.repository.createTask(taskId, docId);

    setImmediate(() => {
      this.run(taskId, docId, traceId).catch((error) => {
        log.error(traceId, "rule extraction background task crashed", {
          task_id: taskId,
          doc_id: docId,
          ...errorDetail(error),
        });
      });
    });

    return { task_id: taskId, status: "processing" };
  }

  private async run(taskId: string, docId: string, traceId: string): Promise<void> {
    const startedAt = Date.now();
    log.info(traceId, "rule extraction started", { task_id: taskId, doc_id: docId });

    try {
      const chunks = await fetchChunksByDocId(docId, traceId);
      const rules = extractRulesFromChunks(chunks);
      const writtenCount = await this.repository.upsertRules(rules);
      await this.repository.completeTask(taskId, writtenCount);

      log.info(traceId, "rule extraction completed", {
        task_id: taskId,
        doc_id: docId,
        chunk_count: chunks.length,
        rule_count: writtenCount,
        duration_ms: Date.now() - startedAt,
      });
    } catch (error) {
      const detail = errorDetail(error);
      const message = typeof detail.message === "string" && detail.message ? detail.message : JSON.stringify(detail);
      await this.repository.failTask(taskId, message);
      log.error(traceId, "rule extraction failed", {
        task_id: taskId,
        doc_id: docId,
        ...detail,
        duration_ms: Date.now() - startedAt,
      });
    }
  }
}
