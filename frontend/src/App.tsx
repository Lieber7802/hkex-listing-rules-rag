import { useRef, useEffect, useMemo } from 'react';
import { Header } from './components/Header';
import { UserMessage } from './components/UserMessage';
import { AssistantMessage } from './components/AssistantMessage';
import { EvidencePanel } from './components/EvidencePanel';
import { InputBar } from './components/InputBar';
import { useChat } from './hooks/useChat';
import type { Citation } from './types/api';
import { BookOpen } from 'lucide-react';

const SAMPLE_QUERIES = [
  {
    label: 'What is a connected transaction?',
    query: 'What is a connected transaction?',
  },
  {
    label: 'What are the disclosure requirements under Chapter 14?',
    query: 'What are the disclosure requirements under Chapter 14?',
  },
  {
    label: 'What is the minimum market capitalization for listing?',
    query: 'What is the minimum market capitalization for listing?',
  },
  {
    label: 'Calculate a size test for a sample acquisition',
    query:
      'Calculate the size test for an acquisition. Transaction consideration is HKD 120 million, issuer total assets HKD 400 million, issuer market capitalization HKD 600 million, issuer net assets HKD 300 million, issuer annual profit HKD 50 million, and issuer revenue HKD 500 million.',
  },
];

export default function App() {
  const { messages, isLoading, sendMessage, newChat } = useChat();
  const scrollRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  // Get citations from the last assistant message for the evidence panel
  const currentCitations: Citation[] = useMemo(() => {
    const lastAssistant = [...messages].reverse().find(m => m.role === 'assistant');
    return lastAssistant?.citations || [];
  }, [messages]);

  const currentToolResults: unknown[] = useMemo(() => {
    const lastAssistant = [...messages].reverse().find(m => m.role === 'assistant');
    return lastAssistant?.toolResults || [];
  }, [messages]);

  return (
    <div className="h-screen flex flex-col bg-slate-50">
      <Header onNewChat={newChat} />

      <div className="flex-1 flex overflow-hidden">
        {/* Chat Panel - Left */}
        <div className="flex-1 flex flex-col min-w-0">
          <div ref={scrollRef} className="flex-1 overflow-y-auto px-6 py-4">
            {messages.length === 0 ? (
              <EmptyState onQuery={sendMessage} />
            ) : (
              <div className="max-w-3xl mx-auto">
                {messages.map(msg =>
                  msg.role === 'user' ? (
                    <UserMessage key={msg.id} content={msg.content} />
                  ) : (
                    <AssistantMessage key={msg.id} message={msg} />
                  )
                )}
              </div>
            )}
          </div>
          <InputBar onSend={sendMessage} disabled={isLoading} />
        </div>

        {/* Evidence Panel - Right */}
        <div className="hidden lg:block w-80 border-l border-slate-200 bg-white">
          <EvidencePanel citations={currentCitations} toolResults={currentToolResults} />
        </div>
      </div>
    </div>
  );
}

function EmptyState({ onQuery }: { onQuery: (q: string) => void }) {
  return (
    <div className="h-full flex items-center justify-center">
      <div className="text-center max-w-md">
        <BookOpen className="w-12 h-12 text-blue-200 mx-auto mb-4" />
        <h2 className="text-lg font-medium text-slate-700 mb-2">
          HKEX Listing Rules Assistant
        </h2>
        <p className="text-sm text-slate-500 mb-6">
          Ask questions about Hong Kong Stock Exchange listing rules, connected transactions, disclosure requirements, and more.
        </p>
        <div className="space-y-2">
          {SAMPLE_QUERIES.map(({ label, query }) => (
            <button
              key={label}
              onClick={() => onQuery(query)}
              className="w-full text-left px-4 py-2.5 text-sm text-slate-600 bg-white border border-slate-200 rounded-lg hover:border-blue-300 hover:bg-blue-50 transition-colors"
            >
              {label}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
