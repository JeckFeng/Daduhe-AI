export interface RuleParameter {
  name?: string;
  operator?: string;
  value?: number;
  unit?: string;
  raw?: string;
}

export interface RuleSource {
  doc_id: string;
  chunk_ids: string[];
  doc_title?: string | null;
  section_number?: string | null;
  section_title?: string | null;
  page_number?: number | null;
}

export interface ExtractedRule {
  rule_id: string;
  title: string;
  content: string;
  category: string | null;
  norm_ref: string | null;
  parameters: RuleParameter;
  source: RuleSource;
  confidence: number;
  doc_id: string;
  chunk_ids: string[];
  content_hash: string;
  created_at?: string;
}

export interface SearchRulesQuery {
  keyword?: string;
  category?: string;
  doc_id?: string;
  page: number;
  page_size: number;
}

export interface ExtractionTask {
  task_id: string;
  doc_id: string;
  status: "processing" | "completed" | "failed";
  error_message?: string | null;
  rule_count: number;
}
