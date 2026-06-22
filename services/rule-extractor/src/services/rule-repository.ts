import { Pool } from "pg";

import { ExtractedRule, ExtractionTask, SearchRulesQuery } from "../types/rule";

export class RuleRepository {
  constructor(private readonly db: Pool) {}

  async createTask(taskId: string, docId: string): Promise<void> {
    await this.db.query(
      `
      INSERT INTO rules.extraction_tasks (task_id, doc_id, status)
      VALUES ($1, $2, 'processing')
      ON CONFLICT (task_id) DO NOTHING
      `,
      [taskId, docId]
    );
  }

  async completeTask(taskId: string, ruleCount: number): Promise<void> {
    await this.db.query(
      `
      UPDATE rules.extraction_tasks
      SET status = 'completed',
          rule_count = $2,
          error_message = NULL,
          updated_at = NOW()
      WHERE task_id = $1
      `,
      [taskId, ruleCount]
    );
  }

  async failTask(taskId: string, message: string): Promise<void> {
    await this.db.query(
      `
      UPDATE rules.extraction_tasks
      SET status = 'failed',
          error_message = $2,
          updated_at = NOW()
      WHERE task_id = $1
      `,
      [taskId, message]
    );
  }

  async findTask(taskId: string): Promise<ExtractionTask | null> {
    const result = await this.db.query<ExtractionTask>(
      `
      SELECT task_id, doc_id, status, error_message, rule_count
      FROM rules.extraction_tasks
      WHERE task_id = $1
      `,
      [taskId]
    );
    return result.rows[0] || null;
  }

  async upsertRules(rules: ExtractedRule[]): Promise<number> {
    if (rules.length === 0) return 0;

    const client = await this.db.connect();
    let insertedOrUpdated = 0;

    try {
      await client.query("BEGIN");
      for (const rule of rules) {
        const result = await client.query(
          `
          INSERT INTO rules.extracted_rules (
            rule_id,
            title,
            content,
            category,
            norm_ref,
            parameters,
            source,
            confidence,
            doc_id,
            chunk_ids,
            content_hash
          )
          VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7::jsonb, $8, $9, $10, $11)
          ON CONFLICT (doc_id, content_hash) DO UPDATE
          SET title = EXCLUDED.title,
              content = EXCLUDED.content,
              category = EXCLUDED.category,
              norm_ref = EXCLUDED.norm_ref,
              parameters = EXCLUDED.parameters,
              source = EXCLUDED.source,
              confidence = EXCLUDED.confidence,
              chunk_ids = EXCLUDED.chunk_ids
          RETURNING rule_id
          `,
          [
            rule.rule_id,
            rule.title,
            rule.content,
            rule.category,
            rule.norm_ref,
            JSON.stringify(rule.parameters),
            JSON.stringify(rule.source),
            rule.confidence,
            rule.doc_id,
            rule.chunk_ids,
            rule.content_hash,
          ]
        );
        insertedOrUpdated += result.rowCount || 0;
      }
      await client.query("COMMIT");
      return insertedOrUpdated;
    } catch (error) {
      await client.query("ROLLBACK");
      throw error;
    } finally {
      client.release();
    }
  }

  async searchRules(query: SearchRulesQuery): Promise<{ items: ExtractedRule[]; total: number }> {
    const offset = (query.page - 1) * query.page_size;
    const params = [
      query.keyword || null,
      query.category || null,
      query.doc_id || null,
      query.page_size,
      offset,
    ];

    const itemsResult = await this.db.query<ExtractedRule>(
      `
      SELECT
        rule_id,
        title,
        content,
        category,
        norm_ref,
        parameters,
        source,
        confidence::float AS confidence,
        doc_id,
        chunk_ids,
        content_hash,
        created_at
      FROM rules.extracted_rules
      WHERE ($1::text IS NULL OR title ILIKE '%' || $1 || '%' OR content ILIKE '%' || $1 || '%')
        AND ($2::text IS NULL OR category = $2)
        AND ($3::text IS NULL OR doc_id = $3)
      ORDER BY created_at DESC
      LIMIT $4 OFFSET $5
      `,
      params
    );

    const countResult = await this.db.query<{ total: string }>(
      `
      SELECT COUNT(*) AS total
      FROM rules.extracted_rules
      WHERE ($1::text IS NULL OR title ILIKE '%' || $1 || '%' OR content ILIKE '%' || $1 || '%')
        AND ($2::text IS NULL OR category = $2)
        AND ($3::text IS NULL OR doc_id = $3)
      `,
      params.slice(0, 3)
    );

    return {
      items: itemsResult.rows,
      total: Number(countResult.rows[0]?.total || 0),
    };
  }
}
