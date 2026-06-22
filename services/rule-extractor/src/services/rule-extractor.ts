import crypto from "crypto";
import { v4 as uuidv4 } from "uuid";

import { Chunk } from "../types/chunk";
import { ExtractedRule, RuleParameter } from "../types/rule";

const NORMATIVE_PATTERN = /(应当|应|必须|不得|禁止|不应|宜|需|需要|须)/;
const CONDITION_PATTERN = /(当|若|如果|如).{1,80}(时|则)/;
const THRESHOLD_PATTERN =
  /(大于等于|小于等于|不小于|不少于|不大于|不超过|超过|大于|小于|低于|高于|≥|<=|≤|>=|>|<)\s*([0-9]+(?:\.[0-9]+)?)\s*([a-zA-Z%％℃°·/一-龥]{0,12})/;

const CATEGORY_HINTS: Array<[RegExp, string]> = [
  [/裂缝|缝宽|开裂/, "混凝土坝/裂缝"],
  [/渗漏|渗流|扬压力|排水/, "混凝土坝/渗漏"],
  [/变形|位移|沉降|挠度/, "混凝土坝/变形"],
  [/混凝土坝|大坝|坝体|坝基/, "混凝土坝/通用"],
  [/监测|观测|巡检|检查/, "安全监测/通用"],
];

export function extractRulesFromChunks(chunks: Chunk[]): ExtractedRule[] {
  return chunks.flatMap((chunk) => extractRulesFromChunk(chunk));
}

export function extractRulesFromChunk(chunk: Chunk): ExtractedRule[] {
  return splitSentences(chunk.chunk_text)
    .filter(isRuleSentence)
    .map((sentence) => buildRule(sentence, chunk));
}

function splitSentences(text: string): string[] {
  return text
    .replace(/\r/g, "")
    .split(/[。；;\n]+/)
    .map((sentence) => sentence.trim())
    .filter((sentence) => sentence.length >= 8);
}

function isRuleSentence(sentence: string): boolean {
  return NORMATIVE_PATTERN.test(sentence) || CONDITION_PATTERN.test(sentence);
}

function buildRule(sentence: string, chunk: Chunk): ExtractedRule {
  const normalized = normalizeSentence(sentence);
  const parameter = extractParameter(normalized);
  const contentHash = hash(`${chunk.chunk_id}:${normalized}`);

  return {
    rule_id: `r-${uuidv4()}`,
    title: buildTitle(normalized, chunk),
    content: normalized,
    category: inferCategory(normalized, chunk),
    norm_ref: inferNormRef(chunk),
    parameters: parameter,
    source: {
      doc_id: chunk.doc_id,
      chunk_ids: [chunk.chunk_id],
      doc_title: chunk.doc_title,
      section_number: chunk.section_number,
      section_title: chunk.section_title,
      page_number: chunk.page_number,
    },
    confidence: scoreRule(normalized, parameter),
    doc_id: chunk.doc_id,
    chunk_ids: [chunk.chunk_id],
    content_hash: contentHash,
  };
}

function normalizeSentence(sentence: string): string {
  return sentence.replace(/\s+/g, " ").replace(/^[0-9.、\s]+/, "").trim();
}

function extractParameter(sentence: string): RuleParameter {
  const match = sentence.match(THRESHOLD_PATTERN);
  if (!match) return {};

  return {
    name: inferParameterName(sentence),
    operator: normalizeOperator(match[1]),
    value: Number(match[2]),
    unit: normalizeUnit(match[3]),
    raw: match[0],
  };
}

function inferParameterName(sentence: string): string {
  if (/宽度|缝宽/.test(sentence)) return "width";
  if (/时间|周期|天|小时|分钟/.test(sentence)) return "duration";
  if (/渗流|流量/.test(sentence)) return "flow";
  if (/位移|沉降|变形/.test(sentence)) return "displacement";
  if (/温度/.test(sentence)) return "temperature";
  return "threshold";
}

function normalizeOperator(operator: string): string {
  const map: Record<string, string> = {
    大于: ">",
    超过: ">",
    高于: ">",
    小于: "<",
    低于: "<",
    大于等于: ">=",
    不小于: ">=",
    不少于: ">=",
    小于等于: "<=",
    不大于: "<=",
    不超过: "<=",
    "≥": ">=",
    ">=": ">=",
    "≤": "<=",
    "<=": "<=",
    ">": ">",
    "<": "<",
  };
  return map[operator] || operator;
}

function normalizeUnit(unit: string | undefined): string | undefined {
  const value = unit?.trim().replace("％", "%");
  return value || undefined;
}

function buildTitle(sentence: string, chunk: Chunk): string {
  const topic = inferTopic(sentence, chunk);
  if (sentence.includes("不得") || sentence.includes("禁止")) return `${topic}禁止性规则`;
  if (CONDITION_PATTERN.test(sentence)) return `${topic}条件处置规则`;
  if (THRESHOLD_PATTERN.test(sentence)) return `${topic}阈值规则`;
  return `${topic}规范要求`;
}

function inferTopic(sentence: string, chunk: Chunk): string {
  if (/裂缝|缝宽/.test(sentence)) return "裂缝";
  if (/渗漏|渗流/.test(sentence)) return "渗漏";
  if (/变形|位移|沉降/.test(sentence)) return "变形";
  if (/监测|观测/.test(sentence)) return "监测";
  return chunk.section_title || "工程";
}

function inferCategory(sentence: string, chunk: Chunk): string | null {
  const text = `${chunk.section_title || ""} ${sentence}`;
  const match = CATEGORY_HINTS.find(([pattern]) => pattern.test(text));
  return match?.[1] || null;
}

function inferNormRef(chunk: Chunk): string | null {
  return chunk.doc_title || null;
}

function scoreRule(sentence: string, parameter: RuleParameter): number {
  let score = 0.72;
  if (NORMATIVE_PATTERN.test(sentence)) score += 0.08;
  if (CONDITION_PATTERN.test(sentence)) score += 0.08;
  if (parameter.value !== undefined) score += 0.07;
  return Math.min(score, 0.95);
}

function hash(value: string): string {
  return crypto.createHash("sha256").update(value).digest("hex");
}
