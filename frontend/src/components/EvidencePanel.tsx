import type { Citation } from '../types/api';
import { FileText, ChevronDown, ChevronUp, Wrench } from 'lucide-react';
import { useState } from 'react';

interface EvidencePanelProps {
  citations: Citation[];
  toolResults: unknown[];
}

export function EvidencePanel({ citations, toolResults }: EvidencePanelProps) {
  if (citations.length === 0 && toolResults.length === 0) {
    return (
      <div className="h-full flex items-center justify-center text-slate-400 text-sm">
        <p>Citations and tool results will appear here after a query is sent.</p>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto p-4 space-y-3">
      {citations.length > 0 && (
        <div>
          <h3 className="text-sm font-medium text-slate-700 mb-2 flex items-center gap-1.5">
            <FileText className="w-4 h-4" />
            Citations ({citations.length})
          </h3>
          <div className="space-y-2">
            {citations.map((c, i) => (
              <CitationCard key={c.chunk_id || i} citation={c} />
            ))}
          </div>
        </div>
      )}

      {toolResults.length > 0 && (
        <div className="mt-4">
          <h3 className="text-sm font-medium text-slate-700 mb-2 flex items-center gap-1.5">
            <Wrench className="w-4 h-4" />
            Tool Results
          </h3>
          {toolResults.map((result, i) => (
            <div key={i} className="bg-slate-50 border border-slate-200 rounded-lg p-3 text-xs font-mono overflow-x-auto">
              <pre>{JSON.stringify(result, null, 2)}</pre>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function CitationCard({ citation }: { citation: Citation }) {
  const [expanded, setExpanded] = useState(false);
  const score = citation.score ? (citation.score * 100).toFixed(1) : null;

  return (
    <div className="bg-white border border-slate-200 rounded-lg overflow-hidden hover:border-blue-300 transition-colors">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full px-3 py-2 flex items-center justify-between text-left"
      >
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            {citation.rule_number && (
              <span className="text-xs font-medium text-blue-700 bg-blue-50 px-1.5 py-0.5 rounded">
                Rule {citation.rule_number}
              </span>
            )}
            {citation.chapter && (
              <span className="text-xs text-slate-500">{citation.chapter}</span>
            )}
          </div>
          {citation.section_title && (
            <p className="text-xs text-slate-600 mt-0.5 truncate">{citation.section_title}</p>
          )}
        </div>
        <div className="flex items-center gap-2 ml-2">
          {score && (
            <span className="text-xs text-slate-400">{score}%</span>
          )}
          {expanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
        </div>
      </button>
      {expanded && (
        <div className="px-3 pb-3 border-t border-slate-100 pt-2">
          <p className="text-xs text-slate-600 leading-relaxed whitespace-pre-wrap">
            {citation.snippet}
          </p>
        </div>
      )}
    </div>
  );
}
