"use client"

import * as React from "react";
import { useState, useEffect } from "react"
import { X, Copy } from "lucide-react"
import { Button } from "@/components/ui/button"
import { apiGetMessageDetails, apiRequeueMessage, apiEditAndRequeueMessage, Message, formatTimestamp } from "@/lib/api"

interface MessageDetailModalProps {
  messageId: string
  onClose: () => void;
  onActionSuccess: () => void;
}

export default function MessageDetailModal({ messageId, onClose, onActionSuccess }: MessageDetailModalProps) {
  const [message, setMessage] = useState<Message | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [isEditMode, setIsEditMode] = useState(false)
  const [editedPayload, setEditedPayload] = useState("")
  const [isRequeuing, setIsRequeuing] = useState(false)

  useEffect(() => {
    const fetchDetails = async () => {
      if (!messageId) return;
      try {
        setLoading(true);
        setError('');
        const response = await apiGetMessageDetails(messageId);
        setMessage(response.data);
        setEditedPayload(JSON.stringify(response.data._source.original_payload, null, 2));
      } catch (err) {
        setError('Failed to load message details.');
        console.error(err);
      } finally {
        setLoading(false);
      }
    };
    fetchDetails();
  }, [messageId]);

  const handleRequeue = async () => {
    if (!message || isRequeuing) return;
    if (!window.confirm("Are you sure you want to re-queue this message?")) return;
    try {
      setIsRequeuing(true);
        await apiRequeueMessage(message._id);
        alert('Message re-queued successfully.');
        onActionSuccess();
        onClose();
    } catch (err) {
        alert('Failed to re-queue message.');
        console.error(err);
      setIsRequeuing(false);
    }
  };

  const handleEditAndRequeue = async () => {
    if (!message || isRequeuing) return;
    try {
        const payload = JSON.parse(editedPayload);
        if (!window.confirm("Are you sure you want to re-queue with the MODIFIED payload?")) return;
      setIsRequeuing(true);
        await apiEditAndRequeueMessage(message._id, payload);
        alert('Message edited and re-queued successfully.');
        onActionSuccess();
        onClose();
    } catch (err) {
        alert('Invalid JSON or failed to re-queue.');
        console.error(err);
      setIsRequeuing(false);
    }
  };

  const handleCopyPayload = () => {
    if (!message) return;
    const payloadStr = JSON.stringify(message._source.original_payload, null, 2);
    navigator.clipboard.writeText(payloadStr).then(() => {
      alert("Payload copied to clipboard!");
    }).catch(err => {
      console.error("Failed to copy: ", err);
    });
  };

  return (
    <>
      {/* Overlay */}
      <div className="fixed inset-0 bg-black bg-opacity-50 z-40" onClick={onClose} />

      {/* Modal */}
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
        <div className="bg-white-primary rounded-lg shadow-lg max-w-2xl w-full max-h-[90vh] flex flex-col">
          {/* Header */}
          <div className="border-b border-gris-blanc p-6 flex justify-between items-start">
            <div>
              <h2 className="text-xl font-semibold text-noir-primary">Message Details</h2>
              <p className="text-sm text-gris-primary mt-1 truncate">ID: {messageId}</p>
            </div>
            <button onClick={onClose} className="text-gris-primary hover:text-noir-primary">
              <X className="w-6 h-6" />
            </button>
          </div>

          {/* Content */}
          <div className="flex-1 overflow-auto p-6 space-y-6">
            {loading && <div className="text-center">Loading...</div>}
            {error && <div className="text-center text-rouge-primary">{error}</div>}
            {message && (
              <>
                {/* Metadata Section */}
                <div>
                  <h3 className="text-sm font-semibold text-noir-primary mb-4">Metadata</h3>
                  <div className="grid grid-cols-2 gap-4 bg-clair-4 p-4 rounded-lg">
                    <div>
                      <p className="text-xs text-gris-primary font-medium mb-1">Service</p>
                      <p className="text-sm text-noir-primary">{message._source.service_name}</p>
                    </div>
                    <div>
                      <p className="text-xs text-gris-primary font-medium mb-1">Timestamp</p>
                      <p className="text-sm text-noir-primary">{formatTimestamp(message._source['@timestamp'])}</p>
                    </div>
                    <div className="col-span-2">
                      <p className="text-xs text-gris-primary font-medium mb-1">Error Reason</p>
                      <p className="text-sm text-noir-primary">{message._source.error_reason}</p>
                    </div>
                  </div>
                </div>

                {/* Payload Section */}
                <div>
                  <div className="flex justify-between items-center mb-4">
                    <h3 className="text-sm font-semibold text-noir-primary">Payload</h3>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={handleCopyPayload}
                      className="text-bleu-primary hover:bg-bleu-light h-8 px-2"
                    >
                      <Copy className="w-4 h-4 mr-1" />
                      Copy
                    </Button>
                  </div>
                  {isEditMode ? (
                    <textarea
                      value={editedPayload}
                      onChange={(e) => setEditedPayload(e.target.value)}
                      className="w-full h-48 p-4 font-mono text-xs border border-gris-blanc rounded-lg bg-white-primary text-noir-primary resize-none"
                    />
                  ) : (
                    <div className="p-4 border border-gris-blanc rounded-lg bg-clair-4 max-h-48 overflow-auto">
                      <pre className="text-xs text-noir-primary whitespace-pre-wrap break-words">
                        {JSON.stringify(message._source.original_payload, null, 2)}
                      </pre>
                    </div>
                  )}
                </div>
              </>
            )}
          </div>

          {/* Footer */}
          {message && (
            <div className="border-t border-gris-blanc p-6 flex justify-end gap-3">
              {isEditMode ? (
                <>
                  <Button
                    variant="outline"
                    onClick={() => setIsEditMode(false)}
                    style={{ borderColor: "var(--gris-primary)" }}
                  >
                    Cancel Edit
                  </Button>
                  <Button
                    style={{ backgroundColor: "var(--bleu-primary)", color: "white" }}
                    onClick={handleEditAndRequeue}
                    className="hover:opacity-90"
                    disabled={isRequeuing}
                  >
                    {isRequeuing ? "Processing..." : "Save & Re-queue"}
                  </Button>
                </>
              ) : (
                <>
                  <Button variant="outline" onClick={onClose}>
                    Close
                  </Button>
                  <Button
                    style={{ backgroundColor: "var(--orange-secondary)", color: "white" }}
                    onClick={() => setIsEditMode(true)}
                    className="hover:opacity-90"
                  >
                    Edit Payload
                  </Button>
                    <Button
                      onClick={handleRequeue}
                      style={{ backgroundColor: "var(--vert-primary)", color: "white" }}
                      className="hover:opacity-90"
                      disabled={isRequeuing}
                    >
                      {isRequeuing ? "Processing..." : "Re-queue Original"}
                  </Button>
                </>
              )}
            </div>
          )}
        </div>
      </div>
    </>
  )
}