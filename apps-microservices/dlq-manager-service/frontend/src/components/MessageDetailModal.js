import React, { useState } from 'react';
import ReactJson from 'react-json-view';
import { apiRequeueMessage, apiEditAndRequeueMessage } from '../api';

function MessageDetailModal({ message, onClose, onActionSuccess }) {
    const [isEditing, setIsEditing] = useState(false);
    const [editedPayload, setEditedPayload] = useState(JSON.stringify(message._source.original_payload, null, 2));

    const handleRequeue = async () => {
        if (!window.confirm("Are you sure you want to re-queue this message?")) return;
        try {
            await apiRequeueMessage(message._id);
            alert('Message re-queued successfully.');
            onActionSuccess();
            onClose();
        } catch (err) {
            alert('Failed to re-queue message.');
        }
    };

    const handleEditAndRequeue = async () => {
        try {
            const payload = JSON.parse(editedPayload);
            if (!window.confirm("Are you sure you want to re-queue with the MODIFIED payload?")) return;
            await apiEditAndRequeueMessage(message._id, { new_payload: payload });
            alert('Message edited and re-queued successfully.');
            onActionSuccess();
            onClose();
        } catch (err) {
            alert('Invalid JSON or failed to re-queue.');
        }
    };


    return (
        <div className="modal-backdrop" onClick={onClose}>
            <div className="modal-content" onClick={e => e.stopPropagation()}>
                <h2>Message Details ({message._id})</h2>
                
                <div className="metadata">
                    <p><strong>Service:</strong> {message._source.service_name}</p>
                    <p><strong>Timestamp:</strong> {message._source['@timestamp']}</p>
                    <p><strong>Error:</strong> {message._source.error_reason}</p>
                </div>
                
                <h3>Original Payload</h3>
                <div className="payload-viewer">
                    {isEditing ? (
                        <textarea 
                            value={editedPayload} 
                            onChange={(e) => setEditedPayload(e.target.value)}
                        />
                    ) : (
                        <ReactJson src={message._source.original_payload} theme="monokai" collapsed={1} />
                    )}
                </div>

                <div className="modal-actions">
                    <button onClick={onClose}>Close</button>
                    {isEditing ? (
                        <>
                            <button onClick={() => setIsEditing(false)}>Cancel Edit</button>
                            <button onClick={handleEditAndRequeue}>Save & Re-queue</button>
                        </>
                    ) : (
                        <>
                            <button onClick={() => setIsEditing(true)}>Edit Payload</button>
                            <button onClick={handleRequeue}>Re-queue Original</button>
                        </>
                    )}
                </div>
            </div>
        </div>
    );
}

export default MessageDetailModal;