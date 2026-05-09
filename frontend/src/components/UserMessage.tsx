interface UserMessageProps {
  content: string;
}

export function UserMessage({ content }: UserMessageProps) {
  return (
    <div className="flex justify-end mb-4">
      <div className="max-w-[75%] bg-blue-600 text-white px-4 py-3 rounded-2xl rounded-br-md shadow-sm">
        <p className="text-sm whitespace-pre-wrap">{content}</p>
      </div>
    </div>
  );
}
