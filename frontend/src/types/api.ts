export interface QueryRequest {
  query: string;
  conversation_id?: string | null;
}

export interface Citation {
  chunk_id: string;
  document_id: string;
  rule_number?: string | null;
  section_title?: string | null;
  chapter?: string | null;
  source_path: string;
  snippet: string;
  score?: number | null;
}

export interface ChatResponse {
  query_type: string;
  answer: string;
  citations: Citation[];
  retrieved_chunks: unknown[];
  uncertainty_note?: string | null;
  confidence_level?: string | null;
  tool_calls: unknown[];
  tool_results: unknown[];
  conversation_id?: string | null;
  turn_number?: number | null;
}

export interface SSEEvent {
  event: string;
  data: Record<string, unknown>;
}

export interface ProgressStep {
  label: string;
  status: 'pending' | 'active' | 'done';
  detail?: string;
}

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  citations?: Citation[];
  toolResults?: unknown[];
  confidenceLevel?: string;
  isStreaming?: boolean;
  progress?: ProgressStep[];
}
