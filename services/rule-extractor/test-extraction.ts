import { Pool } from "pg";
import { extractRulesFromChunks } from "./src/services/rule-extractor";
import { runMigrations } from "./src/db/migrations";
import { Chunk } from "./src/types/chunk";
import { ExtractedRule } from "./src/types/rule";

const DB = {
  host: "localhost",
  port: 5434,
  user: "daduhe",
  password: "gis31415",
  database: "mydatabase",
};

interface RawChunkRow {
  chunk_id: string;
  doc_id: string;
  chunk_index: number | null;
  chunk_text: string;
  page_number: number | null;
  section_title: string | null;
  section_number: string | null;
  char_start: number | null;
  char_end: number | null;
  token_count: number | null;
  doc_title: string | null;
  doc_type: string | null;
}

async function main() {
  const pool = new Pool(DB);

  // 1. 跑迁移，确保 rules schema 和表存在
  console.log("=== Step 1: Run migrations ===");
  await runMigrations(pool);
  console.log("Migrations done.\n");

  // 2. 从数据库读取 chunks（关联 documents 获取 title）
  console.log("=== Step 2: Fetch chunks from metadata.chunks ===");
  const { rows } = await pool.query<RawChunkRow>(
    `SELECT c.*, d.title AS doc_title, d.doc_type
     FROM metadata.chunks c
     JOIN metadata.documents d ON c.doc_id = d.doc_id
     ORDER BY c.doc_id, c.chunk_index`
  );
  console.log(`Fetched ${rows.length} chunks from ${new Set(rows.map((r) => r.doc_id)).size} document(s).\n`);

  // 3. 映射为 Chunk 类型
  const chunks: Chunk[] = rows.map((r) => ({
    chunk_id: r.chunk_id,
    doc_id: r.doc_id,
    chunk_index: r.chunk_index ?? undefined,
    chunk_text: r.chunk_text,
    page_number: r.page_number,
    section_title: r.section_title,
    section_number: r.section_number,
    char_start: r.char_start,
    char_end: r.char_end,
    token_count: r.token_count,
    doc_title: r.doc_title,
    doc_type: r.doc_type,
  }));

  // 4. 执行规则抽取
  console.log("=== Step 3: Extract rules from chunks ===");
  const rules: ExtractedRule[] = extractRulesFromChunks(chunks);
  console.log(`Extracted ${rules.length} rule(s).\n`);

  if (rules.length === 0) {
    console.log("No rules extracted. Exiting.");
    await pool.end();
    return;
  }

  // 打印每条规则
  for (const r of rules) {
    console.log("─".repeat(60));
    console.log(`ID:         ${r.rule_id}`);
    console.log(`Title:      ${r.title}`);
    console.log(`Content:    ${r.content}`);
    console.log(`Category:   ${r.category || "-"}`);
    console.log(`Params:     ${JSON.stringify(r.parameters)}`);
    console.log(`Confidence: ${r.confidence.toFixed(2)}`);
    console.log(`Source:     doc=${r.source.doc_title} page=${r.source.page_number} section=${r.source.section_title}`);
  }
  console.log("─".repeat(60) + "\n");

  // 5. 写入数据库
  console.log("=== Step 4: Upsert rules into rules.extracted_rules ===");
  const client = await pool.connect();
  let written = 0;
  try {
    await client.query("BEGIN");
    for (const rule of rules) {
      const result = await client.query(
        `INSERT INTO rules.extracted_rules (
          rule_id, title, content, category, norm_ref, parameters,
          source, confidence, doc_id, chunk_ids, content_hash
        ) VALUES ($1,$2,$3,$4,$5,$6::jsonb,$7::jsonb,$8,$9,$10,$11)
        ON CONFLICT (doc_id, content_hash) DO UPDATE
        SET title = EXCLUDED.title,
            content = EXCLUDED.content,
            category = EXCLUDED.category,
            norm_ref = EXCLUDED.norm_ref,
            parameters = EXCLUDED.parameters,
            source = EXCLUDED.source,
            confidence = EXCLUDED.confidence,
            chunk_ids = EXCLUDED.chunk_ids
        RETURNING rule_id`,
        [
          rule.rule_id, rule.title, rule.content, rule.category,
          rule.norm_ref, JSON.stringify(rule.parameters),
          JSON.stringify(rule.source), rule.confidence,
          rule.doc_id, rule.chunk_ids, rule.content_hash,
        ]
      );
      written += result.rowCount || 0;
    }
    await client.query("COMMIT");
    console.log(`Written ${written} rule(s) to database.\n`);
  } catch (error) {
    await client.query("ROLLBACK");
    throw error;
  } finally {
    client.release();
  }

  // 6. 验证
  console.log("=== Step 5: Verify ===");
  const { rows: verify } = await pool.query(
    `SELECT rule_id, title, confidence::float, doc_id, category
     FROM rules.extracted_rules ORDER BY doc_id, confidence DESC`
  );
  console.log(`Total rules in DB: ${verify.length}`);
  for (const r of verify) {
    console.log(`  [${r.category || "-"}] ${r.title} (confidence: ${r.confidence.toFixed(2)})`);
  }

  await pool.end();
  console.log("\nDone.");
}

main().catch((error) => {
  console.error("Test failed:", error);
  process.exit(1);
});
