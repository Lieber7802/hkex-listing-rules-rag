import type { ProgressStep } from '../types/api';
import { Check, Loader2 } from 'lucide-react';

interface ProgressIndicatorProps {
  steps: ProgressStep[];
  isStreaming: boolean;
}

export function ProgressIndicator({ steps, isStreaming }: ProgressIndicatorProps) {
  if (steps.length === 0) return null;

  return (
    <div className="mt-2 ml-1 space-y-1">
      {steps.map((step, i) => (
        <div key={i} className="flex items-center gap-2 text-xs text-slate-500">
          {step.status === 'done' ? (
            <Check className="w-3 h-3 text-green-500" />
          ) : (
            <Loader2 className="w-3 h-3 text-blue-500 animate-spin" />
          )}
          <span>{step.label}</span>
          {step.detail && (
            <span className="text-slate-400">({step.detail})</span>
          )}
        </div>
      ))}
      {isStreaming && steps.every(s => s.status === 'done') && (
        <div className="flex items-center gap-2 text-xs text-slate-400">
          <Loader2 className="w-3 h-3 text-blue-500 animate-spin" />
          <span>Generating answer...</span>
        </div>
      )}
    </div>
  );
}
