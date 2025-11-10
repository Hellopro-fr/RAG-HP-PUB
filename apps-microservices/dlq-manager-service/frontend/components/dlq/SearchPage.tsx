"use client"

import { useState, useEffect, useCallback } from "react"
import { SearchIcon } from "lucide-react"
import { Button } from "@/components/ui/button"
import MessageList from "./MessageList"
import Pagination from "./Pagination"
import MessageDetailModal from "./MessageDetailModal";
import { apiSearchMessages, apiBulkRequeue, apiBulkArchive, apiRequeueByFilter, Message } from "@/lib/api";

const loadFiltersFromStorage = () => {
    try {
        const stored = localStorage.getItem('dlq-filters-v2');
        const filters = stored ? JSON.parse(stored) : {};
        if (!filters.status) {
            filters.status = 'New';
        }
        return filters;
    } catch (e) {
        console.error("Could not parse filters from localStorage", e);
        return { status: 'New' };
    }
};

const saveFiltersToStorage = (filters: any) => localStorage.setItem('dlq-filters-v2', JSON.stringify(filters));

export default function SearchPage() {
  const [filters, setFilters] = useState(loadFiltersFromStorage);
  const [searchTerm, setSearchTerm] = useState("")
  const [messages, setMessages] = useState<Message[]>([])
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [currentPage, setCurrentPage] = useState(1)
  const [totalResults, setTotalResults] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null);

  const [selectedMessageId, setSelectedMessageId] = useState<string | null>(null);

  const itemsPerPage = 20

  const fetchMessages = useCallback(async (page = 1) => {
    setLoading(true);
    setError(null);
    setSelectedIds(new Set());
    try {
      const response = await apiSearchMessages({ 
          filters, 
          searchTerm, 
          page: page, 
          pageSize: itemsPerPage 
      });
      setMessages(response.data.messages);
      setTotalResults(response.data.total);
      saveFiltersToStorage(filters);
    } catch (err) {
      setError('Failed to fetch messages.');
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, [filters, searchTerm]);

  useEffect(() => {
    fetchMessages(currentPage);
  }, [currentPage, fetchMessages]);

  const handleSearch = (e?: React.FormEvent) => {
    e?.preventDefault();
    if (currentPage === 1) {
        fetchMessages(1);
    } else {
        setCurrentPage(1);
    }
  };

  const handleFilterChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    setFilters((prev: any) => ({ ...prev, [e.target.name]: e.target.value }));
  };
  
  const handleSelectAll = (checked: boolean) => {
    if (checked) {
      setSelectedIds(new Set(messages.map((m) => m._id)))
    } else {
      setSelectedIds(new Set())
    }
  }

  const handleToggleSelect = (id: string) => {
    const newSelected = new Set(selectedIds)
    if (newSelected.has(id)) {
      newSelected.delete(id)
    } else {
      newSelected.add(id)
    }
    setSelectedIds(newSelected)
  }

  const handleBulkAction = async (action: 'requeue' | 'archive') => {
    const ids = Array.from(selectedIds);
    if (ids.length === 0) return;
    const actionVerb = action === 'requeue' ? 're-queue' : 'archive';

    if (!window.confirm(`Are you sure you want to ${actionVerb} ${ids.length} selected messages?`)) return;

    try {
        if (action === 'requeue') {
            const rateStr = prompt("Enter messages per second (e.g., 10). Leave blank for no limit.", "10");
            const rate = rateStr ? parseInt(rateStr, 10) : undefined;
            if (rateStr && isNaN(rate)) {
                alert("Invalid number for rate limit.");
                return;
            }
            await apiBulkRequeue(ids, rate);
        } else if (action === 'archive') {
            await apiBulkArchive(ids);
        }
        alert(`Successfully started to ${actionVerb} messages.`);
        fetchMessages(currentPage);
    } catch (err) {
        alert(`Failed to ${actionVerb} messages.`);
        console.error(err);
    }
  };

  const handleRequeueByFilter = async () => {
      if (!window.confirm(`Are you sure you want to re-queue all messages matching the current filter? This could be up to ${totalResults} messages.`)) return;
      try {
          const rateStr = prompt("Enter messages per second (e.g., 10). Leave blank for no limit.", "10");
          const rate = rateStr ? parseInt(rateStr, 10) : undefined;
          if (rateStr && isNaN(rate)) {
              alert("Invalid number for rate limit.");
              return;
          }
          await apiRequeueByFilter(filters, searchTerm, rate);
          alert('Re-queue by filter process started successfully.');
          fetchMessages(1);
      } catch (err) {
          alert('Failed to start re-queue by filter.');
          console.error(err);
      }
  };

  return (
    <div className="p-8 space-y-6">
      {/* Filter Bar */}
      <form onSubmit={handleSearch} className="bg-white-primary rounded-lg border border-gris-blanc p-6 space-y-4">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {/* Search Input */}
          <div>
            <label className="block text-sm font-medium text-noir-primary mb-2">Search Term</label>
            <div className="relative">
              <SearchIcon className="absolute left-3 top-3 w-4 h-4 text-gris-primary" />
              <input
                type="text"
                placeholder="Search messages..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="w-full pl-10 pr-4 py-2 border border-gris-blanc rounded-lg bg-white-primary text-noir-primary"
              />
            </div>
          </div>

          {/* Service Names */}
          <div>
            <label className="block text-sm font-medium text-noir-primary mb-2">Services (comma-separated)</label>
            <input
              type="text"
              name="service_names"
              placeholder="e.g., service-a,service-b"
              value={filters.service_names || ''}
              onChange={handleFilterChange}
              className="w-full px-4 py-2 border border-gris-blanc rounded-lg bg-white-primary text-noir-primary"
            />
          </div>

          {/* Status Dropdown */}
          <div>
            <label className="block text-sm font-medium text-noir-primary mb-2">Status</label>
            <select
              name="status"
              value={filters.status || ''}
              onChange={handleFilterChange}
              className="w-full px-4 py-2 border border-gris-blanc rounded-lg bg-white-primary text-noir-primary"
            >
              <option value="">Any Status</option>
              <option value="New">New</option>
              <option value="Re-queued">Re-queued</option>
              <option value="Re-queued (Legacy)">Re-queued (Legacy)</option>
              <option value="Archived">Archived</option>
            </select>
          </div>
        </div>

        <Button
          type="submit"
          style={{ backgroundColor: "var(--bleu-primary)", color: "white" }}
          className="w-full hover:opacity-90"
        >
          <SearchIcon className="w-4 h-4 mr-2" />
          Search
        </Button>
      </form>

      {/* Action Bar */}
      <div className="flex justify-between items-center bg-white-primary rounded-lg border border-gris-blanc p-4">
        <div className="text-sm text-gris-primary">
          {selectedIds.size > 0 ? (
            <>
              <strong>{selectedIds.size}</strong> of <strong>{totalResults}</strong> selected
            </>
          ) : (
            <>
              <strong>{totalResults}</strong> results found
            </>
          )}
        </div>

        <div className="flex gap-3">
          {selectedIds.size > 0 ? (
            <>
              <Button onClick={() => handleBulkAction('requeue')} style={{ backgroundColor: "var(--vert-primary)", color: "white" }} className="hover:opacity-90">
                Re-queue Selected
              </Button>
              <Button onClick={() => handleBulkAction('archive')} style={{ backgroundColor: "var(--gris-primary)", color: "white" }} className="hover:opacity-90">
                Archive Selected
              </Button>
            </>
          ) : (
            <Button
              onClick={handleRequeueByFilter}
              style={{
                backgroundColor: "var(--bleu-primary)",
                color: "white",
                opacity: totalResults === 0 ? 0.5 : 1,
              }}
              disabled={totalResults === 0}
              className="hover:opacity-90"
            >
              Re-queue All Matching
            </Button>
          )}
        </div>
      </div>

      {/* Message List */}
      {loading && <div className="text-center p-8">Loading messages...</div>}
      {error && <div className="p-4 text-center text-rouge-primary bg-rouge-light rounded-lg">{error}</div>}
      {!loading && !error && (
        <MessageList
            messages={messages}
            selectedIds={selectedIds}
            onSelectAll={(checked) => handleSelectAll(checked)}
            onToggleSelect={handleToggleSelect}
            onMessageSelect={(id) => setSelectedMessageId(id)}
            allSelected={selectedIds.size === messages.length && messages.length > 0}
        />
      )}

      {/* Pagination */}
      <Pagination
        currentPage={currentPage}
        totalItems={totalResults}
        itemsPerPage={itemsPerPage}
        onPageChange={setCurrentPage}
      />

      {selectedMessageId && (
        <MessageDetailModal
          messageId={selectedMessageId}
          onClose={() => setSelectedMessageId(null)}
          onActionSuccess={() => fetchMessages(currentPage)}
        />
      )}
    </div>
  )
}
