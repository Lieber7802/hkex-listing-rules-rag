import { useState, useCallback } from 'react';
import type { Message, Citation } from '../types/api';
import { streamChat } from '../services/api';

let messageIdCounter = 0;
function genId() {
  return `msg-${Date.now()}-${++messageIdCounter}`;
}

export function useChat() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(
    () => localStorage.getItem('hkex_conversation_id')
  );
  const [isLoading, setIsLoading] = useState(false);

  const sendMessage = useCallback(async (query: string) => {
    if (!query.trim() || isLoading) return;

    // Add user message
    const userMsg: Message = { id: genId(), role: 'user', content: query };
    const assistantId = genId();
    const assistantMsg: Message = {
      id: assistantId,
      role: 'assistant',
      content: '',
      isStreaming: true,
      progress: [],
      citations: [],
      toolResults: [],
    };

    setMessages(prev => [...prev, userMsg, assistantMsg]);
    setIsLoading(true);

    try {
      const events = streamChat(query, conversationId);

      for await (const { event, data } of events) {
        setMessages(prev => {
          const msgs = [...prev];
          const idx = msgs.findIndex(m => m.id === assistantId);
          if (idx === -1) return prev;
          const msg = { ...msgs[idx] };

          switch (event) {
            case 'routing_complete':
              msg.progress = [...(msg.progress || []), {
                label: `Route: ${data.query_type || 'direct'}`,
                status: 'done',
              }];
              break;

            case 'retrieval_complete':
              msg.progress = [...(msg.progress || []), {
                label: `Retrieved ${data.num_chunks || 0} chunks`,
                status: 'done',
                detail: data.top_score ? `top score: ${(data.top_score as number).toFixed(3)}` : undefined,
              }];
              break;

            case 'tool_executed':
              msg.progress = [...(msg.progress || []), {
                label: `Tool: ${data.tool_name}`,
                status: 'done',
                detail: data.success ? 'success' : 'failed',
              }];
              if (data.output_preview) {
                msg.toolResults = [...(msg.toolResults || []), data];
              }
              break;

            case 'answer_chunk':
              msg.content += (data.content as string) || '';
              break;

            case 'citations':
              if (data.citations) {
                msg.citations = (data.citations as Citation[]) || [];
              }
              break;

            case 'verification_complete':
              msg.confidenceLevel = data.confidence_level as string;
              msg.progress = [...(msg.progress || []), {
                label: 'Verification completed',
                status: 'done',
                detail: `confidence: ${data.confidence_level || 'N/A'}`,
              }];
              break;

            case 'done': {
              msg.isStreaming = false;
              const newCid = data.conversation_id as string;
              if (newCid) {
                setConversationId(newCid);
                localStorage.setItem('hkex_conversation_id', newCid);
              }
              break;
            }

            case 'error':
              msg.content = `Error: ${data.message || 'Unknown error'}`;
              msg.isStreaming = false;
              break;
          }

          msgs[idx] = msg;
          return msgs;
        });
      }
    } catch (err) {
      setMessages(prev => {
        const msgs = [...prev];
        const idx = msgs.findIndex(m => m.id === assistantId);
        if (idx !== -1) {
          msgs[idx] = {
            ...msgs[idx],
            content: `Connection error: ${err instanceof Error ? err.message : 'Unknown'}`,
            isStreaming: false,
          };
        }
        return msgs;
      });
    } finally {
      setIsLoading(false);
    }
  }, [conversationId, isLoading]);

  const newChat = useCallback(() => {
    setMessages([]);
    setConversationId(null);
    localStorage.removeItem('hkex_conversation_id');
  }, []);

  return { messages, isLoading, conversationId, sendMessage, newChat };
}
