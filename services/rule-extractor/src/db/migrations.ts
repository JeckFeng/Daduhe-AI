import { Pool } from "pg";

export async function runMigrations(pool: Pool): Promise<void> {
  await pool.query(`
    CREATE SCHEMA IF NOT EXISTS rules;

    CREATE TABLE IF NOT EXISTS rules.extraction_tasks (
      task_id VARCHAR(64) PRIMARY KEY,
      doc_id VARCHAR(64) NOT NULL,
      status VARCHAR(32) NOT NULL,
      error_message TEXT,
      rule_count INTEGER DEFAULT 0,
      created_at TIMESTAMPTZ DEFAULT NOW(),
      updated_at TIMESTAMPTZ DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS rules.extracted_rules (
      rule_id VARCHAR(64) PRIMARY KEY,
      title TEXT NOT NULL,
      content TEXT NOT NULL,
      category TEXT,
      norm_ref TEXT,
      parameters JSONB DEFAULT '{}'::jsonb,
      source JSONB NOT NULL,
      confidence NUMERIC(4,3) DEFAULT 0.800,
      doc_id VARCHAR(64) NOT NULL,
      chunk_ids TEXT[] NOT NULL,
      content_hash VARCHAR(64) NOT NULL,
      created_at TIMESTAMPTZ DEFAULT NOW(),
      UNIQUE (doc_id, content_hash)
    );

    CREATE INDEX IF NOT EXISTS idx_extraction_tasks_doc_id
      ON rules.extraction_tasks(doc_id);

    CREATE INDEX IF NOT EXISTS idx_rules_doc_id
      ON rules.extracted_rules(doc_id);

    CREATE INDEX IF NOT EXISTS idx_rules_category
      ON rules.extracted_rules(category);

    CREATE INDEX IF NOT EXISTS idx_rules_content
      ON rules.extracted_rules USING gin(to_tsvector('simple', content));
  `);
}
