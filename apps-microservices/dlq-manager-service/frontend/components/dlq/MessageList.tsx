"use client"

import { Checkbox } from "@/components/ui/checkbox"
import { Button } from "@/components/ui/button"
import { Message, formatTimestamp } from "@/lib/api";

interface MessageListProps {
  messages: Message[]
  selectedIds: Set<string>
  onSelectAll: (checked: boolean) => void
  onToggleSelect: (id: string) => void
  onMessageSelect: (messageId: string) => void;
  allSelected: boolean
}

export default function MessageList({
  messages,
  selectedIds,
  onSelectAll,
  onToggleSelect,
  onMessageSelect,
  allSelected,
}: MessageListProps) {

  const getStatusBadgeStyle = (status?: string) => {
    const s = status || 'New';
    const styles: Record<string, { bg: string; text: string }> = {
      New: { bg: "var(--bleu-light)", text: "var(--bleu-primary)" },
      "Re-queued": { bg: "var(--vert-light)", text: "var(--vert-primary)" },
      "Re-queued (Edited)": { bg: "var(--vert-light)", text: "var(--vert-primary)" },
      "Re-queued (Legacy)": { bg: "var(--clair-3)", text: "var(--noir-primary)" },
      Archived: { bg: "var(--clair-4)", text: "var(--gris-primary)" },
    }
    return styles[s] || { bg: "var(--clair-3)", text: "var(--noir-primary)" }
  }

  if (messages.length === 0) {
    return <div className="p-8 text-center text-gris-primary">No messages found for the selected criteria.</div>
  }

  return (
    <>
      <div className="bg-white-primary rounded-lg border border-gris-blanc overflow-hidden">
        <table className="w-full">
          <thead>
            <tr className="border-b border-gris-blanc bg-clair-4">
              <th className="w-12 p-4">
                <Checkbox checked={allSelected} onCheckedChange={onSelectAll} className="rounded" />
              </th>
              <th className="px-6 py-4 text-left text-sm font-semibold text-noir-primary">Timestamp</th>
              <th className="px-6 py-4 text-left text-sm font-semibold text-noir-primary">Service</th>
              <th className="px-6 py-4 text-left text-sm font-semibold text-noir-primary">Error Reason</th>
              <th className="px-6 py-4 text-left text-sm font-semibold text-noir-primary">Status</th>
              <th className="px-6 py-4 text-left text-sm font-semibold text-noir-primary">Actions</th>
            </tr>
          </thead>
          <tbody>
            {messages.map((message) => {
              const status = message._source.status || (message._source.requeued_at ? 'Re-queued (Legacy)' : 'New');
              const statusStyle = getStatusBadgeStyle(status);
              return (
                <tr key={message._id} className="border-b border-gris-blanc hover:bg-clair-4 transition-colors">
                  <td className="w-12 p-4">
                    <Checkbox
                      checked={selectedIds.has(message._id)}
                      onCheckedChange={() => onToggleSelect(message._id)}
                      className="rounded"
                    />
                  </td>
                  <td className="px-6 py-4 text-sm text-gris-primary">{formatTimestamp(message._source['@timestamp'])}</td>
                  <td className="px-6 py-4 text-sm text-noir-primary font-medium">{message._source.service_name}</td>
                  <td className="px-6 py-4 text-sm text-gris-primary max-w-xs truncate" title={message._source.error_reason}>
                    {message._source.error_reason}
                  </td>
                  <td className="px-6 py-4 text-sm">
                    <span
                      className="px-3 py-1 rounded-full text-xs font-medium"
                      style={{
                        backgroundColor: statusStyle.bg,
                        color: statusStyle.text,
                      }}
                    >
                      {status}
                    </span>
                  </td>
                  <td className="px-6 py-4 text-sm">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => onMessageSelect(message._id)}
                      style={{ borderColor: "var(--bleu-primary)", color: "var(--bleu-primary)" }}
                    >
                      Details
                    </Button>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </>
  )
}
