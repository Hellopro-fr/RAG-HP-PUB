"use client"

import * as React from "react";
import { useState, useEffect, useCallback } from "react"
import { Calendar, SearchIcon, Loader2, Info } from "lucide-react"
import { Button } from "@/components/ui/button"
import MessageList from "./MessageList"
import Pagination from "./Pagination"
import MessageDetailModal from "./MessageDetailModal";
import { apiGetDashboardStats, apiSearchMessages, apiBulkRequeue, apiBulkArchive, apiRequeueByFilter, apiArchiveByFilter, Message } from "@/lib/api";
import { MultiSelect, MultiSelectOption } from "./MultiSelect";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { DateTimePicker } from "./DateTimePicker";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";

interface Filters {
    service_names: string[];
    status: string[];
    date_start?: Date;
    date_end?: Date;
}

const loadFiltersFromStorage = (): Omit<Filters, 'date_start' | 'date_end'> => {
    try {
        const stored = localStorage.getItem('dlq-filters-v3');
        const filters = stored ? JSON.parse(stored) : {};
        // We don't persist dates from local storage
        delete filters.date_start;
        delete filters.date_end;

        if (!filters.status || !Array.isArray(filters.status)) {
            filters.status = ['New'];
        }
        if (!filters.service_names) {
            filters.service_names = [];
        }
        return filters;
    } catch (e) {
        console.error("Could not parse filters from localStorage", e);
        return { status: ['New'], service_names: [] };
    }
};

const saveFiltersToStorage = (filters: Filters) => {
    const storableFilters = { ...filters };
    delete storableFilters.date_start;
    delete storableFilters.date_end;
    localStorage.setItem('dlq-filters-v3', JSON.stringify(storableFilters));
}

const statusOptions: MultiSelectOption[] = [
    { value: 'New', label: 'New' },
    { value: 'Re-queued', label: 'Re-queued' },
    { value: 'Archived', label: 'Archived' },
];

export default function SearchPage() {
  const [filters, setFilters] = useState<Filters>(loadFiltersFromStorage());
  const [searchTerm, setSearchTerm] = useState("")
  const [messages, setMessages] = useState<Message[]>([])
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [currentPage, setCurrentPage] = useState(1)
  const [totalResults, setTotalResults] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null);

  const [selectedMessageId, setSelectedMessageId] = useState<string | null>(null);
  const [serviceOptions, setServiceOptions] = useState<MultiSelectOption[]>([]);
  const [pageSize, setPageSize] = useState(20);
  const [loadingAction, setLoadingAction] = useState<string | null>(null);

  useEffect(() => {
    apiGetDashboardStats().then(response => {
        const options = response.data.by_service.map(bucket => ({
            value: bucket.key,
            label: bucket.key,
        }));
        setServiceOptions(options);
    }).catch(err => {
        console.error("Failed to fetch service names for filters", err);
    })
  }, []);

  const fetchMessages = useCallback(async (page = 1) => {
    setLoading(true);
    setError(null);
    setSelectedIds(new Set());
    try {
      const activeFilters: Record<string, any> = {};
      
      (Object.keys(filters) as Array<keyof Filters>).forEach(key => {
        const value = filters[key];
        if (key === 'date_start' || key === 'date_end') {
          if (value instanceof Date) {
            activeFilters[key] = value.toISOString();
          }
        } else if (Array.isArray(value) && value.length > 0) {
          activeFilters[key] = value;
        }
      });

      const response = await apiSearchMessages({
          filters: activeFilters, 
          searchTerm, 
          page: page, 
          pageSize: pageSize 
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
  }, [filters, searchTerm, pageSize]);

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

  const handleFilterChange = <K extends keyof Filters>(name: K, value: Filters[K]) => {
    setFilters((prev) => ({ ...prev, [name]: value }));
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
    if (loadingAction) {
        alert(`An action (${loadingAction.replace('-', ' ')}) is already in progress. Please wait for it to complete.`);
        return;
    }

    const ids = Array.from(selectedIds);
    if (ids.length === 0) return;
    const actionVerb = action === 'requeue' ? 're-queue' : 'archive';

    if (!window.confirm(`Are you sure you want to ${actionVerb} ${ids.length} selected messages?`)) return;

    const currentAction = action === 'requeue' ? 'requeue-selected' : 'archive-selected';
    setLoadingAction(currentAction);

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
    } finally {
        setLoadingAction(null);
    }
  };

  const handleRequeueByFilter = async () => {
      if (loadingAction) {
        alert(`An action (${loadingAction.replace('-', ' ')}) is already in progress. Please wait for it to complete.`);
        return;
      }

      if (!window.confirm(`Are you sure you want to re-queue all messages matching the current filter? This could be up to ${totalResults} messages.`)) return;
      
      setLoadingAction('requeue-all');

      try {
          const rateStr = prompt("Enter messages per second (e.g., 10). Leave blank for no limit.", "10");
          const rate = rateStr ? parseInt(rateStr, 10) : undefined;
          if (rateStr && isNaN(rate)) {
              alert("Invalid number for rate limit.");
              setLoadingAction(null); // Reset on user error
              return;
          }
          await apiRequeueByFilter(filters, searchTerm, rate);
          alert('Re-queue by filter process started successfully.');
          fetchMessages(1);
      } catch (err) {
          alert('Failed to start re-queue by filter.');
          console.error(err);
      } finally {
          setLoadingAction(null);
      }
  };

  const handleArchiveByFilter = async () => {
      if (loadingAction) {
          alert(`An action (${loadingAction.replace('-', ' ')}) is already in progress. Please wait for it to complete.`);
          return;
      }

      if (!window.confirm(`Are you sure you want to archive all messages matching the current filter? This could be up to ${totalResults} messages.`)) return;

      setLoadingAction('archive-all');

      try {
          await apiArchiveByFilter(filters, searchTerm);
          alert('Archive by filter process started successfully.');
          fetchMessages(1);
      } catch (err) {
          alert('Failed to start archive by filter.');
          console.error(err);
      } finally {
          setLoadingAction(null);
      }
  };

  return (
    <div className="p-8 space-y-6">
      {/* Filter Bar */}
      <form onSubmit={handleSearch} className="bg-white-primary rounded-lg border border-gris-blanc p-6 space-y-4">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Search Input */}
            <div className="md:col-span-2">
                <label className="block text-sm font-medium text-noir-primary mb-2">Search Term</label>
                <div className="relative flex items-center">
                    <SearchIcon className="absolute left-3 w-4 h-4 text-gris-primary pointer-events-none" />
                    <input
                        type="text"
                        placeholder="Search in payload, error, service..."
                        value={searchTerm}
                        onChange={(e) => setSearchTerm(e.target.value)}
                        className="w-full pl-10 pr-10 py-2 border border-gris-blanc rounded-lg bg-white-primary text-noir-primary"
                    />
                    <Popover>
                        <PopoverTrigger asChild>
                            <button type="button" className="absolute right-3 text-gris-primary hover:text-bleu-primary transition-colors focus:outline-none">
                                <Info className="w-4 h-4" />
                            </button>
                        </PopoverTrigger>
                        <PopoverContent className="w-80 p-4 text-sm bg-white-primary border-gris-blanc shadow-lg" align="end">
                            <h4 className="font-semibold mb-3 text-noir-primary">Search Syntax Guide</h4>
                            <ul className="space-y-2 text-gris-primary">
                                <li><strong>Basic:</strong> <code className="bg-clair-4 px-1 rounded text-noir-primary">timeout</code></li>
                                <li><strong>Exact Phrase:</strong> <code className="bg-clair-4 px-1 rounded text-noir-primary">"connection refused"</code></li>
                                <li><strong>Wildcard:</strong> <code className="bg-clair-4 px-1 rounded text-noir-primary">*timeout*</code> or <code className="bg-clair-4 px-1 rounded text-noir-primary">serv*</code></li>
                                <li><strong>Specific Field:</strong> <code className="bg-clair-4 px-1 rounded text-noir-primary">service_name:api-recherche-service</code></li>
                                <li><strong>Logical Operators:</strong> <code className="bg-clair-4 px-1 rounded text-noir-primary">AND</code>, <code className="bg-clair-4 px-1 rounded text-noir-primary">OR</code>, <code className="bg-clair-4 px-1 rounded text-noir-primary">NOT</code></li>
                                <li><strong>Payload Search:</strong> <code className="bg-clair-4 px-1 rounded text-noir-primary">original_payload.id:123</code></li>
                            </ul>
                        </PopoverContent>
                    </Popover>
                </div>
            </div>

            {/* Service Names */}
            <div>
                <label className="block text-sm font-medium text-noir-primary mb-2">Services</label>
                <MultiSelect
                    options={serviceOptions}
                    selected={filters.service_names}
                    onChange={(selected) => handleFilterChange('service_names', selected)}
                    placeholder="Select services..."
                />
            </div>

            {/* Status Dropdown */}
            <div>
                <label className="block text-sm font-medium text-noir-primary mb-2">Status</label>
                <MultiSelect
                    options={statusOptions}
                    selected={filters.status}
                    onChange={(selected) => handleFilterChange('status', selected)}
                    placeholder="Select statuses..."
                />
            </div>

            <div>
                <label className="block text-sm font-medium text-noir-primary mb-2">From Date</label>
                <DateTimePicker
                    date={filters.date_start}
                    setDate={(date) => handleFilterChange('date_start', date)}
                />
            </div>
            <div>
                <label className="block text-sm font-medium text-noir-primary mb-2">To Date</label>
                <DateTimePicker
                    date={filters.date_end}
                    setDate={(date) => handleFilterChange('date_end', date)}
                />
            </div>
        </div>

        <Button
          type="submit"
          style={{ backgroundColor: "var(--bleu-primary)", color: "white" }}
          className="w-full hover:opacity-90"
          disabled={!!loadingAction}
        >
          <SearchIcon className="w-4 h-4 mr-2" />
          Search
        </Button>
      </form>

      {/* Action Bar */}
      <div className="flex justify-between items-center bg-white-primary rounded-lg border border-gris-blanc p-4">
        <div className="flex items-center gap-4 text-sm text-gris-primary">
            <span>
                {selectedIds.size > 0 ? (
                    <><strong>{selectedIds.size}</strong> of <strong>{totalResults.toLocaleString()}</strong> selected</>
                ) : (
                    <><strong>{totalResults.toLocaleString()}</strong> results found</>
                )}
            </span>
            <div className="flex items-center gap-2">
                <label htmlFor="pageSize" className="text-sm font-medium">Per Page:</label>
                <Select value={pageSize.toString()} onValueChange={(val) => { setPageSize(Number(val)); setCurrentPage(1); }}>
                    <SelectTrigger className="w-20 h-8">
                        <SelectValue placeholder="Page size" />
                    </SelectTrigger>
                    <SelectContent>
                        <SelectItem value="10">10</SelectItem>
                        <SelectItem value="20">20</SelectItem>
                        <SelectItem value="50">50</SelectItem>
                        <SelectItem value="100">100</SelectItem>
                    </SelectContent>
                </Select>
            </div>
        </div>


        <div className="flex gap-3">
          {selectedIds.size > 0 ? (
            <>
              <Button 
                onClick={() => handleBulkAction('requeue')} 
                style={{ backgroundColor: "var(--vert-primary)", color: "white" }} 
                className="hover:opacity-90 w-40"
                disabled={!!loadingAction}
              >
                {loadingAction === 'requeue-selected' && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                Re-queue Selected
              </Button>
              <Button 
                onClick={() => handleBulkAction('archive')} 
                style={{ backgroundColor: "var(--gris-primary)", color: "white" }} 
                className="hover:opacity-90 w-40"
                disabled={!!loadingAction}
              >
                {loadingAction === 'archive-selected' && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                Archive Selected
              </Button>
            </>
          ) : (
            <>
              <Button
                onClick={handleArchiveByFilter}
                style={{ backgroundColor: "var(--gris-primary)", color: "white" }}
                disabled={totalResults === 0 || !!loadingAction}
                className="hover:opacity-90 disabled:opacity-50 w-48"
              >
                {loadingAction === 'archive-all' && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                Archive All Matching
              </Button>
              <Button
                onClick={handleRequeueByFilter}
                style={{ backgroundColor: "var(--bleu-primary)", color: "white" }}
                disabled={totalResults === 0 || !!loadingAction}
                className="hover:opacity-90 disabled:opacity-50 w-48"
              >
                {loadingAction === 'requeue-all' && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                Re-queue All Matching
              </Button>
            </>
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
        itemsPerPage={pageSize}
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