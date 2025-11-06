import React, { useState, useEffect } from 'react';
import { apiSearchMessages, apiRequeueByFilter, apiBulkRequeue, apiBulkArchive } from '../api';
import MessageList from './MessageList';
import MessageDetailModal from './MessageDetailModal';
import Pagination from './Pagination';

const loadFiltersFromStorage = () => {
    try {
        const stored = localStorage.getItem('dlq-filters');
        const filters = stored ? JSON.parse(stored) : {};
        // If there's no status, or if status is an empty string, default to 'New'
        if (!filters.status) {
            filters.status = 'New';
        }
        return filters;
    } catch (e) {
        console.error("Could not parse filters from localStorage", e);
        // On any error, return the safe default
        return { status: 'New' };
    }
};

const saveFiltersToStorage = (filters) => localStorage.setItem('dlq-filters', JSON.stringify(filters));

function SearchPage() {
    const [messages, setMessages] = useState([]);
    const [total, setTotal] = useState(0);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');
    
    const [filters, setFilters] = useState(loadFiltersFromStorage);
    const [searchTerm, setSearchTerm] = useState('');
    const [page, setPage] = useState(1);
    const pageSize = 20;

    const [selectedMessageId, setSelectedMessageId] = useState(null);
    const [selectedIds, setSelectedIds] = useState(new Set());
    
    const fetchMessages = async (currentPage) => {
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
        fetchMessages(page);
    }, [page]);
    
    const handleFilterChange = (e) => {
        setFilters(prev => ({ ...prev, [e.target.name]: e.target.value }));
    };

    const handleSearch = (e) => {
        e.preventDefault();
        setPage(1);
        fetchMessages(1);
    };

    const handlePageChange = (newPage) => {
        setPage(newPage);
    };

    const handleRequeueByFilter = async () => {
        if (window.confirm(`Are you sure you want to re-queue all messages matching the current filter? This could be up to ${total} messages.`)) {
            try {
                const rate = prompt("Enter messages per second (e.g., 10). Leave blank for no limit.", "10");
                await apiRequeueByFilter({ filters, searchTerm, rate_limit_per_second: parseInt(rate) || null });
                alert('Re-queue by filter process started.');
                handleSearch({ preventDefault: () => {} });
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
            handleSearch({ preventDefault: () => {} });
        } catch (err) {
            alert(`Failed to ${actionVerb} messages.`);
        }
    };

    return (
        <div className="space-y-6">
            <form onSubmit={handleSearch} className="bg-white-primary p-4 rounded-lg shadow-md border border-clair-2 space-y-4 md:space-y-0 md:flex md:items-center md:space-x-4">
                <input type="text" value={searchTerm} onChange={e => setSearchTerm(e.target.value)} placeholder="Search in payload, error..." className="w-full md:flex-grow bg-white-light border border-gris-blanc rounded-md px-3 py-2 text-noir-primary focus:ring-bleu-primary focus:border-bleu-primary"/>
                <input type="text" name="service_names" value={filters.service_names || ''} onChange={handleFilterChange} placeholder="Service name (comma-sep)" className="w-full md:w-auto bg-white-light border border-gris-blanc rounded-md px-3 py-2 text-noir-primary focus:ring-bleu-primary focus:border-bleu-primary"/>
                <select name="status" value={filters.status || ''} onChange={handleFilterChange} className="w-full md:w-auto bg-white-light border border-gris-blanc rounded-md px-3 py-2 text-noir-primary focus:ring-bleu-primary focus:border-bleu-primary">
                    <option value="">Any Status</option>
                    <option value="New">New</option>
                    <option value="Re-queued">Re-queued</option>
                    <option value="Re-queued (Legacy)">Re-queued (Legacy)</option>
                    <option value="Archived">Archived</option>
                </select>
                <button type="submit" className="w-full md:w-auto px-4 py-2 bg-bleu-primary text-white-primary rounded-md hover:bg-bleu-heavy transition-colors">Search</button>
            </form>

            <div className="bg-white-primary rounded-lg shadow-md border border-clair-2">
                <div className="p-4 flex items-center justify-between border-b border-clair-2">
                    <div className="text-sm text-gris-primary">
                        {selectedIds.size > 0 ? `${selectedIds.size} of ${total} selected` : `${total} messages found`}
                    </div>
                    <div>
                        {selectedIds.size > 0 ? (
                            <div className="space-x-2">
                                <button onClick={() => handleBulkAction('requeue')} className="px-3 py-1 text-sm bg-vert-light text-vert-secondary font-semibold rounded-md hover:bg-vert-primary hover:text-white-primary">Re-queue Selected</button>
                                <button onClick={() => handleBulkAction('archive')} className="px-3 py-1 text-sm bg-clair-3 text-gris-primary font-semibold rounded-md hover:bg-gris-primary hover:text-white-primary">Archive Selected</button>
                            </div>
                        ) : (
                            <button onClick={handleRequeueByFilter} disabled={total === 0} className="px-3 py-1 text-sm bg-bleu-light text-bleu-primary font-semibold rounded-md hover:bg-bleu-primary hover:text-white-primary disabled:opacity-50 disabled:cursor-not-allowed">Re-queue All Matching</button>
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
                 <div className="p-4 border-t border-clair-2">
                    <Pagination 
                        currentPage={page}
                        totalPages={Math.ceil(total / pageSize)}
                        onPageChange={handlePageChange}
                    />
                </div>
            </div>

            {selectedMessageId && (
                <MessageDetailModal 
                    messageId={selectedMessageId} 
                    onClose={() => setSelectedMessageId(null)}
                    onActionSuccess={() => handleSearch({ preventDefault: () => {} })}
                />
            )}
        </div>
    );
}

export default SearchPage;