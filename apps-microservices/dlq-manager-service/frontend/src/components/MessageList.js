import React from 'react';
import { format } from 'date-fns';

function MessageList({ messages, onMessageSelect, selectedIds, setSelectedIds }) {

    const handleSelect = (id) => {
        const newSelectedIds = new Set(selectedIds);
        if (newSelectedIds.has(id)) {
            newSelectedIds.delete(id);
        } else {
            newSelectedIds.add(id);
        }
        setSelectedIds(newSelectedIds);
    };

    const handleSelectAll = (e) => {
        if (e.target.checked) {
            const allIds = messages.map(m => m._id);
            setSelectedIds(new Set(allIds));
        } else {
            setSelectedIds(new Set());
        }
    };
    
    if (!messages || messages.length === 0) {
        return <div className="no-results">No messages found.</div>;
    }

    return (
        <table className="message-list">
            <thead>
                <tr>
                    <th><input type="checkbox" onChange={handleSelectAll} /></th>
                    <th>Timestamp</th>
                    <th>Service</th>
                    <th>Error Reason</th>
                    <th>Status</th>
                    <th>Actions</th>
                </tr>
            </thead>
            <tbody>
                {messages.map(msg => (
                    <tr key={msg._id}>
                        <td><input type="checkbox" checked={selectedIds.has(msg._id)} onChange={() => handleSelect(msg._id)} /></td>
                        <td>{format(new Date(msg._source['@timestamp']), 'yyyy-MM-dd HH:mm:ss')}</td>
                        <td>{msg._source.service_name}</td>
                        <td className="error-reason">{msg._source.error_reason.substring(0, 150)}...</td>
                        <td>{msg._source.status || 'New'}</td>
                        <td>
                            <button onClick={() => onMessageSelect(msg)}>Details</button>
                        </td>
                    </tr>
                ))}
            </tbody>
        </table>
    );
}

export default MessageList;