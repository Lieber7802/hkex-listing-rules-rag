import { MessageSquare, Plus } from 'lucide-react';

interface HeaderProps {
  onNewChat: () => void;
}

export function Header({ onNewChat }: HeaderProps) {
  return (
    <header className="bg-white border-b border-slate-200 px-6 py-3 flex items-center justify-between">
      <div className="flex items-center gap-3">
        <MessageSquare className="w-6 h-6 text-blue-700" />
        <h1 className="text-lg font-semibold text-slate-800">
          HKEX Listing Rules Compliance Assistant
        </h1>
      </div>
      <button
        onClick={onNewChat}
        className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-slate-600 hover:text-blue-700 hover:bg-blue-50 rounded-lg transition-colors"
      >
        <Plus className="w-4 h-4" />
        New Chat
      </button>
    </header>
  );
}
