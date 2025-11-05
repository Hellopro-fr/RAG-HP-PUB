import React, { useState, useEffect } from 'react';
import ReactJson from 'react-json-view';
import { apiGetMessageDetails, apiRequeueMessage, apiEditAndRequeueMessage } from '../api';

function MessageDetailModal({ messageId, onClose, onActionSuccess }) {
    const [message, setMessage] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');

    const [isEditing, setIsEditing] = useState(false);
    const [editedPayload, setEditedPayload] = useState('');

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
        <div className="fixed inset-0 bg-noir-heavy bg-opacity-75 flex items-center justify-center z-50 transition-opacity" onClick={onClose}>
            <div className="bg-bleu-noir rounded-lg shadow-2xl w-full max-w-4xl h-5/6 flex flex-col border border-gris-primary/20" onClick={e => e.stopPropagation()}>
                <div className="p-6 border-b border-gris-primary/20">
                    <h2 className="text-xl font-bold text-white-primary">Message Details</h2>
                    <p className="text-sm text-gris-clair truncate">ID: {messageId}</p>
                </div>
                
                <div className="p-6 flex-grow overflow-y-auto">
                    {loading && <div className="text-center">Loading message details...</div>}
                    {error && <div className="bg-rouge-light text-rouge-primary p-4 rounded-md">{error}</div>}
                    
                    {message && (
                        <div className="space-y-4">
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
                                <div><strong className="text-gris-clair block">Service:</strong> {message._source.service_name}</div>
                                <div><strong className="text-gris-clair block">Timestamp:</strong> {message._source['@timestamp']}</div>
                                <div className="col-span-full"><strong className="text-gris-clair block">Error:</strong> {message._source.error_reason}</div>
                            </div>
                            
                            <div>
                                <h3 className="font-bold text-white-primary mb-2">Original Payload</h3>
                                <div className="bg-bleu-noir-2 p-4 rounded-md h-96 overflow-y-auto border border-gris-primary/20">
                                    {isEditing ? (
                                        <textarea 
                                            value={editedPayload} 
                                            onChange={(e) => setEditedPayload(e.target.value)}
                                            className="w-full h-full bg-transparent text-white-primary font-mono text-sm border-0 focus:ring-0"
                                        />
                                    ) : (
                                        <ReactJson src={message._source.original_payload} theme="ocean" style={{backgroundColor: 'transparent'}} collapsed={1} />
                                    )}
                                </div>
                            </div>
                        </div>
                    )}
                </div>

                {message && (
                     <div className="p-6 border-t border-gris-primary/20 flex justify-end space-x-4">
                        <button onClick={onClose} className="px-4 py-2 bg-gris-primary text-white-primary rounded-md hover:bg-gris-clair transition-colors">Close</button>
                        {isEditing ? (
                            <>
                                <button onClick={() => setIsEditing(false)} className="px-4 py-2 bg-noir-primary text-gris-clair rounded-md hover:bg-noir-heavy transition-colors">Cancel Edit</button>
                                <button onClick={handleEditAndRequeue} className="px-4 py-2 bg-bleu-primary text-white-primary rounded-md hover:bg-bleu-heavy transition-colors">Save & Re-queue</button>
                            </>
                        ) : (
                            <>
                                <button onClick={() => setIsEditing(true)} className="px-4 py-2 bg-orange-secondary text-white-primary rounded-md hover:bg-orange-heavy transition-colors">Edit Payload</button>
                                <button onClick={handleRequeue} className="px-4 py-2 bg-vert-primary text-white-primary rounded-md hover:bg-vert-secondary transition-colors">Re-queue Original</button>
                            </>
                        )}
                    </div>
                )}
            </div>
        </div>
    );
}

export default MessageDetailModal;