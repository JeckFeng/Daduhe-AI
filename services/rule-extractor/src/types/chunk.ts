export interface Chunk {
  chunk_id: string;
  doc_id: string;
  chunk_index?: number;
  chunk_text: string;
  page_number?: number | null;
  section_title?: string | null;
  section_number?: string | null;
  char_start?: number | null;
  char_end?: number | null;
  token_count?: number | null;
  doc_title?: string | null;
  doc_type?: string | null;
}

export interface ChunkListResponse {
  code: number;
  data?: {
    items: Chunk[];
    total: number;
    page: number;
    page_size: number;
  };
  message?: string;
}
