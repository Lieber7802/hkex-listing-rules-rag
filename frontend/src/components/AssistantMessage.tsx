import type { Message } from '../types/api';
import { ProgressIndicator } from './ProgressIndicator';
import { Bot } from 'lucide-react';
import ReactMarkdown from 'react-markdown';

interface AssistantMessageProps {
  message: Message;
}

export function AssistantMessage({ message }: AssistantMessageProps) {
  const { content, isStreaming, progress, confidenceLevel } = message;

  return (
    <div className="flex gap-3 mb-4">
      <div className="flex-shrink-0 w-8 h-8 rounded-full bg-slate-100 flex items-center justify-center">
        <Bot className="w-4 h-4 text-slate-600" />
      </div>
      <div className="flex-1 max-w-[85%]">
        <div className="bg-white border border-slate-200 px-4 py-3 rounded-2xl rounded-tl-md shadow-sm">
          {content ? (
            <div className={`markdown-message text-sm text-slate-800 leading-relaxed ${isStreaming ? 'cursor-blink' : ''}`}>
              <ReactMarkdown>{content}</ReactMarkdown>
            </div>
          ) : isStreaming ? (
            <div className="flex items-center gap-2 text-sm text-slate-400">
              <span className="animate-pulse">Thinking...</span>
            </div>
          ) : null}

          {confidenceLevel && !isStreaming && (
            <div className="mt-2 pt-2 border-t border-slate-100">
              <span className={`text-xs px-2 py-0.5 rounded-full ${
                confidenceLevel === 'high' ? 'bg-green-100 text-green-700' :
                confidenceLevel === 'medium' ? 'bg-yellow-100 text-yellow-700' :
                'bg-red-100 text-red-700'
              }`}>
                Confidence: {confidenceLevel}
              </span>
            </div>
          )}
        </div>

        {progress && progress.length > 0 && (
          <ProgressIndicator steps={progress} isStreaming={isStreaming || false} />
        )}
      </div>
    </div>
  );
}
