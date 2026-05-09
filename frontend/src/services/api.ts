import type { SSEEvent } from '../types/api';

/**
 * Stream chat via SSE (POST /v2/chat/stream).
 * Yields parsed SSE events as they arrive.
 */
export async function* streamChat(
  query: string,
  conversationId?: string | null
): AsyncGenerator<SSEEvent> {
  const response = await fetch('/v2/chat/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      query,
      conversation_id: conversationId || null,
    }),
  });

  if (!response.ok) {
    throw new Error(`HTTP ${response.status}: ${response.statusText}`);
  }

  const reader = response.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let currentEvent = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop()!; // Keep incomplete line in buffer

    for (const line of lines) {
      if (line.startsWith('event: ')) {
        currentEvent = line.slice(7).trim();
      } else if (line.startsWith('data: ') && currentEvent) {
        try {
          const data = JSON.parse(line.slice(6));
          yield { event: currentEvent, data };
        } catch {
          // Skip malformed JSON
        }
        currentEvent = '';
      }
    }
  }
}

/**
 * Check API health.
 */
export async function checkHealth(): Promise<{ status: string; version: string }> {
  const res = await fetch('/v2/health');
  return res.json();
}
