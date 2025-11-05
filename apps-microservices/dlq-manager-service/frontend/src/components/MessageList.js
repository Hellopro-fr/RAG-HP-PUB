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
    
    const StatusBadge = ({ status }) => {
        const s = status || 'New';
        let colorClasses = 'bg-gris-clair text-noir-primary';
        if (s === 'New') colorClasses = 'bg-bleu-light text-bleu-heavy';
        if (s.includes('Re-queued')) colorClasses = 'bg-vert-light text-vert-secondary';
        if (s === 'Archived') colorClasses = 'bg-clair-3 text-gris-primary';

        return <span className={`px-2 py-1 text-xs font-semibold rounded-full ${colorClasses}`}>{s}</span>
    };

    if (messages.length === 0) {
        return <div className="text-center py-12 text-gris-primary">No messages found.</div>;
    }

    return (
        <div className="overflow-x-auto">
            <table className="w-full text-sm text-left text-noir-primary">
                <thead className="text-xs text-gris-primary uppercase bg-clair-3">
                    <tr>
                        <th scope="col" className="p-4">
                            <input type="checkbox" onChange={handleSelectAll} className="w-4 h-4 text-orange-primary bg-clair-2 border-gris-blanc rounded focus:ring-orange-secondary"/>
                        </th>
                        <th scope="col" className="px-6 py-3">Timestamp</th>
                        <th scope="col" className="px-6 py-3">Service</th>
                        <th scope="col" className="px-6 py-3">Error Reason</th>
                        <th scope="col" className="px-6 py-3">Status</th>
                        <th scope="col" className="px-6 py-3">Actions</th>
                    </tr>
                </thead>
                <tbody>
                    {messages.map(msg => (
                        <tr key={msg._id} className="border-b border-clair-2 hover:bg-clair-3">
                            <td className="w-4 p-4">
                                 <input type="checkbox" checked={selectedIds.has(msg._id)} onChange={() => handleSelect(msg._id)} className="w-4 h-4 text-orange-primary bg-clair-2 border-gris-blanc rounded focus:ring-orange-secondary"/>
                            </td>
                            <td className="px-6 py-4 whitespace-nowrap text-gris-primary">{format(new Date(msg._source['@timestamp']), 'yyyy-MM-dd HH:mm:ss')}</td>
                            <td className="px-6 py-4 font-medium">{msg._source.service_name}</td>
                            <td className="px-6 py-4 max-w-md truncate" title={msg._source.error_reason}>{msg._source.error_reason}</td>
                            <td className="px-6 py-4">
                                <StatusBadge status={msg._source.status} />
                            </td>
                            <td className="px-6 py-4">
                                <button onClick={() => onMessageSelect(msg)} className="font-medium text-orange-primary hover:underline">Details</button>
                            </td>
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
}

export default MessageList;