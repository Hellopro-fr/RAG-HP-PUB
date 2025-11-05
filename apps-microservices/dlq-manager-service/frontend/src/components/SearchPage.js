import React, { useState, useEffect } from 'react';
import { apiSearchMessages, apiRequeueByFilter, apiBulkRequeue, apiBulkArchive } from '../api';
import MessageList from './MessageList';
import MessageDetailModal from './MessageDetailModal';

// Functionality #10: Saved Filters (using localStorage)
const saveFiltersToStorage = (filters) => localStorage.setItem('dlq-filters', JSON.stringify(filters));

function SearchPage() {
    const [messages, setMessages] = useState([]);
    const [total, setTotal] = useState(0);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');
    
    // Default to a focused view of 'New' messages unless otherwise specified in localStorage
    const [filters, setFilters] = useState(() => {
        const stored = localStorage.getItem('dlq-filters');
        return stored ? JSON.parse(stored) : { status: 'New' };
    });
    const [searchTerm, setSearchTerm] = useState('');
    const [page, setPage] = useState(1);
    const pageSize = 50;

    const [selectedMessageId, setSelectedMessageId] = useState(null); // Changed from object to ID
    const [selectedIds, setSelectedIds] = useState(new Set());
    
    const [viewMode, setViewMode] = useState('individual'); // 'individual' or 'grouped'

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
        <div className="search-page">
            <div className="filter-panel">
                <form onSubmit={handleSearch}>
                    <input type="text" value={searchTerm} onChange={e => setSearchTerm(e.target.value)} placeholder="Search in payload, error..." />
                    <input type="text" name="service_names" value={filters.service_names || ''} onChange={handleFilterChange} placeholder="Service name (comma-sep)" />
                    <select name="status" value={filters.status || ''} onChange={handleFilterChange}>
                        <option value="">Any Status</option>
                        <option value="New">New</option>
                        <option value="Re-queued">Re-queued</option>
                        <option value="Re-queued (Legacy)">Re-queued (Legacy)</option>
                        <option value="Archived">Archived</option>
                    </select>
                    <input type="datetime-local" name="date_start" value={filters.date_start || ''} onChange={handleFilterChange} />
                    <input type="datetime-local" name="date_end" value={filters.date_end || ''} onChange={handleFilterChange} />
                    <button type="submit">Search</button>
                </form>
            </div>

            <div className="actions-bar">
                {selectedIds.size > 0 ? (
                    <>
                        <span>{selectedIds.size} selected</span>
                        <button onClick={() => handleBulkAction('requeue')}>Re-queue Selected</button>
                        <button onClick={() => handleBulkAction('archive')}>Archive Selected</button>
                    </>
                ) : (
                    <button onClick={handleRequeueByFilter} disabled={total === 0}>Re-queue All Matching ({total})</button>
                )}
            </div>

            {loading && <div>Loading...</div>}
            {error && <div className="error-message">{error}</div>}
            
            <MessageList 
                messages={messages} 
                onMessageSelect={(message) => setSelectedMessageId(message._id)} // Pass ID instead of object
                selectedIds={selectedIds}
                setSelectedIds={setSelectedIds}
            />

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