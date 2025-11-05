import React, { useState, useEffect } from 'react';
import { apiSearchMessages, apiRequeueByFilter, apiBulkRequeue, apiBulkArchive } from '../api';
import MessageList from './MessageList';
import MessageDetailModal from './MessageDetailModal';

const loadFiltersFromStorage = () => {
    const stored = localStorage.getItem('dlq-filters');
    // FIX: Ensure a default is always present if nothing is stored or if stored is empty
    if (stored) {
        return JSON.parse(stored);
    }
    return { status: 'New' };
};

// Functionality #10: Saved Filters (using localStorage)
const saveFiltersToStorage = (filters) => localStorage.setItem('dlq-filters', JSON.stringify(filters));

function SearchPage() {
    const [messages, setMessages] = useState([]);
    const [total, setTotal] = useState(0);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');
    
    const [filters, setFilters] = useState(loadFiltersFromStorage);
    const [searchTerm, setSearchTerm] = useState('');
    const [page, setPage] = useState(1);
    const pageSize = 50;

    const [selectedMessageId, setSelectedMessageId] = useState(null); // Changed from object to ID
    const [selectedIds, setSelectedIds] = useState(new Set());
    
    const fetchMessages = async (currentPage = 1) => {
        try {
            setLoading(true);
            setError('');
            const response = await apiSearchMessages({ filters, searchTerm, page: currentPage, pageSize });
            setMessages(response.data.messages);
            setTotal(response.data.total);
            saveFiltersToStorage(filters);
        } catch (err) {
            setError('Failed to fetch messages.');
            console.error(err);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchMessages(1);
    }, []); // Empty dependency array ensures this runs only once
    
    const handleFilterChange = (e) => {
        setFilters(prev => ({ ...prev, [e.target.name]: e.target.value }));
    };

    const handleSearch = (e) => {
        e.preventDefault();
        setPage(1); // Reset to page 1 for every new search
        fetchMessages(1);
    };

    const handleRequeueByFilter = async () => {
        if (window.confirm(`Are you sure you want to re-queue all messages matching the current filter? This could be up to ${total} messages.`)) {
            try {
                // Functionality #11: Throttled Re-queuing
                const rate = prompt("Enter messages per second (e.g., 10). Leave blank for no limit.", "10");
                await apiRequeueByFilter({ filters, searchTerm, rate_limit_per_second: parseInt(rate) || null });
                alert('Re-queue by filter process started.');
                handleSearch({ preventDefault: () => {} }); // Refresh search results
            } catch (err) {
                alert('Failed to start re-queue by filter.');
            }
        }
    };

    const handleBulkAction = async (action) => {
        const ids = Array.from(selectedIds);
        if (ids.length === 0) return;

        const actionVerb = action === 'requeue' ? 're-queue' : 'archive';
        if (!window.confirm(`Are you sure you want to ${actionVerb} ${ids.length} selected messages?`)) return;

        try {
            if (action === 'requeue') {
                const rate = prompt("Enter messages per second (e.g., 10). Leave blank for no limit.", "10");
                await apiBulkRequeue({ message_ids: ids, rate_limit_per_second: parseInt(rate) || null });
            } else if (action === 'archive') {
                await apiBulkArchive({ message_ids: ids });
            }
            setSelectedIds(new Set());
            handleSearch({ preventDefault: () => {} }); // Refresh search results
        } catch (err) {
            alert(`Failed to ${actionVerb} messages.`);
        }
    };


    return (
        <div className="space-y-6">
            <form onSubmit={handleSearch} className="bg-bleu-noir p-4 rounded-lg shadow-lg border border-gris-primary/20 space-y-4 md:space-y-0 md:flex md:items-center md:space-x-4">
                <input type="text" value={searchTerm} onChange={e => setSearchTerm(e.target.value)} placeholder="Search in payload, error..." className="w-full md:w-1/4 bg-bleu-noir-2 border border-gris-primary/30 rounded-md px-3 py-2 text-white-primary focus:ring-orange-primary focus:border-orange-primary"/>
                <input type="text" name="service_names" value={filters.service_names || ''} onChange={handleFilterChange} placeholder="Service name (comma-sep)" className="w-full md:w-1/4 bg-bleu-noir-2 border border-gris-primary/30 rounded-md px-3 py-2 text-white-primary focus:ring-orange-primary focus:border-orange-primary"/>
                <select name="status" value={filters.status || ''} onChange={handleFilterChange} className="w-full md:w-auto bg-bleu-noir-2 border border-gris-primary/30 rounded-md px-3 py-2 text-white-primary focus:ring-orange-primary focus:border-orange-primary">
                    <option value="">Any Status</option>
                    <option value="New">New</option>
                    <option value="Re-queued">Re-queued</option>
                    <option value="Re-queued (Legacy)">Re-queued (Legacy)</option>
                    <option value="Archived">Archived</option>
                </select>
                <button type="submit" className="w-full md:w-auto px-4 py-2 bg-orange-primary text-white-primary rounded-md hover:bg-orange-heavy transition-colors">Search</button>
            </form>

            <div className="bg-bleu-noir p-4 rounded-lg shadow-lg border border-gris-primary/20">
                <div className="flex items-center justify-between mb-4">
                    <div className="text-sm text-gris-clair">
                        {selectedIds.size > 0 ? `${selectedIds.size} selected` : `${total} messages found`}
                    </div>
                    <div>
                        {selectedIds.size > 0 ? (
                            <div className="space-x-2">
                                <button onClick={() => handleBulkAction('requeue')} className="px-3 py-1 text-sm bg-vert-primary text-white-primary rounded-md hover:bg-vert-secondary">Re-queue Selected</button>
                                <button onClick={() => handleBulkAction('archive')} className="px-3 py-1 text-sm bg-gris-primary text-white-primary rounded-md hover:bg-gris-clair">Archive Selected</button>
                            </div>
                        ) : (
                            <button onClick={handleRequeueByFilter} disabled={total === 0} className="px-3 py-1 text-sm bg-bleu-primary text-white-primary rounded-md hover:bg-bleu-heavy disabled:opacity-50 disabled:cursor-not-allowed">Re-queue All Matching</button>
                        )}
                    </div>
                </div>

                {loading && <div className="text-center p-8">Loading messages...</div>}
                {error && <div className="bg-rouge-light text-rouge-primary p-4 rounded-md">{error}</div>}
                {!loading && !error && (
                    <MessageList 
                        messages={messages} 
                        onMessageSelect={(message) => setSelectedMessageId(message._id)}
                        selectedIds={selectedIds}
                        setSelectedIds={setSelectedIds}
                    />
                )}
            </div>

            {selectedMessageId && ( // Render modal based on ID
                <MessageDetailModal 
                    messageId={selectedMessageId} 
                    onClose={() => setSelectedMessageId(null)}
                    onActionSuccess={() => handleSearch({ preventDefault: () => {} })}
                />
            )}
            
            {/* Pagination controls would go here */}
        </div>
    );
}

export default SearchPage;