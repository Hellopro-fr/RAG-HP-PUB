"use client"

import * as React from "react";
import { useState, useEffect, useCallback, useRef } from "react"
import { Calendar, SearchIcon, Loader2, Info, BookmarkPlus } from "lucide-react"
import { Button } from "@/components/ui/button"
import MessageList from "./MessageList"
import Pagination from "./Pagination"
import MessageDetailModal from "./MessageDetailModal";
import CreateRuleModal from "./CreateRuleModal";
import { apiGetDashboardStats, apiGetServiceNames, apiSearchMessages, apiBulkRequeue, apiBulkArchive, apiRequeueByFilter, apiArchiveByFilter, apiGetTaskStatus, apiGetUniqueErrors, Message, UniqueErrorBucket } from "@/lib/api";
import UniqueErrorsModal from "./UniqueErrorsModal";
import { MultiSelect, MultiSelectOption } from "./MultiSelect";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { DateTimePicker } from "./DateTimePicker";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";

interface Filters {
    service_names: string[];
    status: string[];
    date_start?: Date;
    date_end?: Date;
    error_reason?: string;
}

const loadFiltersFromStorage = (): Omit<Filters, 'date_start' | 'date_end'> => {
    if (typeof window === 'undefined') return { status: ['New'], service_names: [] };
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
    { value: 'Auto-Archived', label: 'Auto-Archived' },
];

export default function SearchPage() {
  const [filters, setFilters] = useState<Filters>(loadFiltersFromStorage);
  const [searchTerm, setSearchTerm] = useState("")
  const [messages, setMessages] = useState<Message[]>([])
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [currentPage, setCurrentPage] = useState(1)
  const [totalResults, setTotalResults] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null);

  const [selectedMessageId, setSelectedMessageId] = useState<string | null>(null);
  const [showCreateRuleModal, setShowCreateRuleModal] = useState(false);
  const [serviceOptions, setServiceOptions] = useState<MultiSelectOption[]>([]);
  const [pageSize, setPageSize] = useState(20);
  const [loadingAction, setLoadingAction] = useState<string | null>(null);

  const ARCHIVED_STATUSES = ['Archived', 'Auto-Archived'];
  const isArchivedOnlyView = filters.status.length > 0 && filters.status.every(s => ARCHIVED_STATUSES.includes(s));

  const [showUniqueErrors, setShowUniqueErrors] = useState(false);
  const [uniqueErrorBuckets, setUniqueErrorBuckets] = useState<UniqueErrorBucket[]>([]);
  const [uniqueErrorTotal, setUniqueErrorTotal] = useState(0);
  const [loadingUniqueErrors, setLoadingUniqueErrors] = useState(false);
  const pollTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Cleanup polling on unmount
  useEffect(() => {
    return () => {
      if (pollTimeoutRef.current) clearTimeout(pollTimeoutRef.current);
    };
  }, []);

  // Fetch service names dynamically based on current status + date filters
  useEffect(() => {
    const debounceTimer = setTimeout(() => {
      const serviceFilters: Record<string, any> = {};
      if (filters.status.length > 0) {
        serviceFilters.status = filters.status;
      }
      if (filters.date_start instanceof Date) {
        serviceFilters.date_start = filters.date_start.toISOString();
      }
      if (filters.date_end instanceof Date) {
        serviceFilters.date_end = filters.date_end.toISOString();
      }

      apiGetServiceNames(serviceFilters).then(response => {
        const options = response.data.services.map(bucket => ({
          value: bucket.key,
          label: bucket.key,
        }));
        setServiceOptions(options);

        // Purge stale service_names that no longer exist in current options
        const validKeys = new Set(options.map((o: { value: string }) => o.value));
        setFilters((prev: Filters) => {
          const cleaned = prev.service_names.filter((s: string) => validKeys.has(s));
          if (cleaned.length !== prev.service_names.length) {
            return { ...prev, service_names: cleaned };
          }
          return prev;
        });
      }).catch(err => {
        console.error("Failed to fetch service names for filters", err);
      });
    }, 300);

    return () => clearTimeout(debounceTimer);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(filters.status), filters.date_start?.getTime(), filters.date_end?.getTime()]);

  // Construct standard JSON filter payload to use consistently
  const getActiveFiltersPayload = useCallback(() => {
    const activeFilters: Record<string, any> = {};
    (Object.keys(filters) as Array<keyof Filters>).forEach(key => {
      const value = filters[key];
      if (key === 'date_start' || key === 'date_end') {
        if (value instanceof Date) {
          activeFilters[key] = value.toISOString();
        }
      } else if (key === 'error_reason') {
        if (value && typeof value === 'string') {
          activeFilters[key] = value;
        }
      } else if (Array.isArray(value) && value.length > 0) {
        activeFilters[key] = value;
      }
    });
    return activeFilters;
  }, [filters]);

  const fetchMessages = useCallback(async (page = 1) => {
    setLoading(true);
    setError(null);
    setSelectedIds(new Set());
    try {
      const activeFilters = getActiveFiltersPayload();
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

  const pollTaskStatus = (taskId: string, successMessage: string) => {
    let attempts = 0;
    const MAX_POLL_ATTEMPTS = 300; // 10 minutes at 2s intervals

    const checkStatus = async () => {
      attempts++;
      try {
        const res = await apiGetTaskStatus(taskId);
        if (res.data.completed) {
          if (res.data.status === "completed") {
              alert(successMessage);
          } else if (res.data.status === "error") {
              alert("The background task encountered an error and stopped prematurely. Please check the backend logs.");
          }
          fetchMessages(1);
          setLoadingAction(null);
          pollTimeoutRef.current = null;
        } else if (attempts >= MAX_POLL_ATTEMPTS) {
          alert("Polling timed out. The task might still be running in the background.");
          setLoadingAction(null);
          pollTimeoutRef.current = null;
        } else {
          pollTimeoutRef.current = setTimeout(checkStatus, 2000);
        }
      } catch (err) {
        console.error("Polling failed", err);
        alert("Failed to confirm task completion. The task might still be running.");
        setLoadingAction(null);
        pollTimeoutRef.current = null;
      }
    };

    checkStatus();
  };

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
            if (rateStr === null) { setLoadingAction(null); return; } // User cancelled
            const rate = rateStr ? parseInt(rateStr, 10) : undefined;
            if (rateStr && isNaN(rate!)) {
                alert("Invalid number for rate limit.");
                setLoadingAction(null);
                return;
            }
            await apiBulkRequeue(ids, rate);
        } else if (action === 'archive') {
            await apiBulkArchive(ids);
        }
        alert(`Successfully processed selected messages.`);
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
          if (rateStr === null) { setLoadingAction(null); return; } // User cancelled
          const rate = rateStr ? parseInt(rateStr, 10) : undefined;
          if (rateStr && isNaN(rate!)) {
              alert("Invalid number for rate limit.");
              setLoadingAction(null);
              return;
          }
          const activeFilters = getActiveFiltersPayload();
          const response = await apiRequeueByFilter(activeFilters, searchTerm, rate);
          
          if (response.data.task_id) {
              pollTaskStatus(response.data.task_id, 'Re-queue by filter process completed successfully.');
          } else {
              alert('Re-queue by filter process started successfully.');
              fetchMessages(1);
              setLoadingAction(null);
          }
      } catch (err) {
          alert('Failed to start re-queue by filter.');
          console.error(err);
          setLoadingAction(null);
      }
  };

  const handleViewUniqueErrors = async () => {
    setShowUniqueErrors(true);
    setLoadingUniqueErrors(true);
    setUniqueErrorBuckets([]);
    setUniqueErrorTotal(0);
    try {
      const activeFilters = getActiveFiltersPayload();
      const response = await apiGetUniqueErrors(activeFilters, searchTerm);
      setUniqueErrorBuckets(response.data.buckets);
      setUniqueErrorTotal(response.data.total_unique);
    } catch (err) {
      console.error("Failed to fetch unique errors", err);
      alert("Failed to fetch unique errors.");
      setShowUniqueErrors(false);
    } finally {
      setLoadingUniqueErrors(false);
    }
  };

  const handleSelectError = (serviceName: string, errorReason: string) => {
    setFilters(prev => ({
      ...prev,
      service_names: [serviceName],
      error_reason: errorReason,
    }));
    setShowUniqueErrors(false);
  };

  const handleArchiveByFilter = async () => {
      if (loadingAction) {
          alert(`An action (${loadingAction.replace('-', ' ')}) is already in progress. Please wait for it to complete.`);
          return;
      }

      if (!window.confirm(`Are you sure you want to archive all messages matching the current filter? This could be up to ${totalResults} messages.`)) return;

      setLoadingAction('archive-all');

      try {
          const activeFilters = getActiveFiltersPayload();
          const response = await apiArchiveByFilter(activeFilters, searchTerm);
          
          if (response.data.task_id) {
              pollTaskStatus(response.data.task_id, 'Archive by filter process completed successfully.');
          } else {
              alert('Archive by filter process started successfully.');
              fetchMessages(1);
              setLoadingAction(null);
          }
      } catch (err) {
          alert('Failed to start archive by filter.');
          console.error(err);
          setLoadingAction(null);
      }
  };

  return (
    <div className="p-4 md:p-8 space-y-6">
      {/* Filter Bar */}
      <form onSubmit={handleSearch} className="bg-white-primary rounded-lg border border-gris-blanc p-4 md:p-6 space-y-4">
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

            {filters.error_reason && (
              <div className="md:col-span-2 flex items-center gap-2">
                <span className="text-sm text-gris-primary">Active Error Filter:</span>
                <span className="inline-flex items-center gap-1 px-3 py-1 rounded-full text-xs font-medium bg-bleu-light text-bleu-primary border border-bleu-primary/20 max-w-full">
                  <span className="truncate">{filters.error_reason}</span>
                  <button
                    type="button"
                    onClick={() => setFilters(prev => ({ ...prev, error_reason: undefined }))}
                    className="ml-1 hover:text-rouge-primary transition-colors shrink-0"
                    aria-label="Clear error filter"
                  >
                    ×
                  </button>
                </span>
              </div>
            )}

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

        <div className="flex flex-col sm:flex-row gap-3 pt-2">
            <Button
                type="submit"
                style={{ backgroundColor: "var(--bleu-primary)", color: "white" }}
                className="w-full sm:flex-1 hover:opacity-90"
                disabled={!!loadingAction}
            >
                <SearchIcon className="w-4 h-4 mr-2" />
                Search
            </Button>
            <Button
                type="button"
                variant="outline"
                style={{ borderColor: "var(--bleu-primary)", color: "var(--bleu-primary)" }}
                className="w-full sm:w-auto hover:bg-bleu-light"
                disabled={!!loadingAction || (!searchTerm && Object.keys(getActiveFiltersPayload()).length === 0)}
                onClick={() => setShowCreateRuleModal(true)}
            >
                <BookmarkPlus className="w-4 h-4 mr-2" />
                Save Search as Rule
            </Button>
        </div>
      </form>

      {/* Action Bar */}
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center bg-white-primary rounded-lg border border-gris-blanc p-4 gap-4">
        <div className="flex flex-col sm:flex-row items-start sm:items-center gap-2 sm:gap-4 text-sm text-gris-primary w-full md:w-auto">
            <span>
                {selectedIds.size > 0 ? (
                    <><strong>{selectedIds.size}</strong> of <strong>{totalResults.toLocaleString()}</strong> selected</>
                ) : (
                    <><strong>{totalResults.toLocaleString()}</strong> results found</>
                )}
            </span>
            <div className="flex items-center gap-2 w-full sm:w-auto justify-between sm:justify-start">
                <label htmlFor="pageSize" className="text-sm font-medium">Per Page:</label>
                <Select value={pageSize.toString()} onValueChange={(val) => { setPageSize(Number(val)); setCurrentPage(1); }}>
                    <SelectTrigger className="w-20 h-8 bg-white-primary">
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


        <div className="flex flex-col sm:flex-row gap-2 sm:gap-3 w-full md:w-auto">
          {selectedIds.size > 0 ? (
            <>
              <Button 
                onClick={() => handleBulkAction('requeue')} 
                style={{ backgroundColor: "var(--vert-primary)", color: "white" }} 
                className="hover:opacity-90 w-full sm:w-auto"
                disabled={!!loadingAction}
              >
                {loadingAction === 'requeue-selected' && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                Re-queue Selected
              </Button>
              {!isArchivedOnlyView && (
                <Button
                  onClick={() => handleBulkAction('archive')}
                  style={{ backgroundColor: "var(--gris-primary)", color: "white" }}
                  className="hover:opacity-90 w-full sm:w-auto"
                  disabled={!!loadingAction}
                >
                  {loadingAction === 'archive-selected' && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                  Archive Selected
                </Button>
              )}
            </>
          ) : (
            <>
              <Button
                onClick={handleViewUniqueErrors}
                variant="outline"
                style={{ borderColor: "var(--bleu-primary)", color: "var(--bleu-primary)" }}
                disabled={totalResults === 0 || !!loadingAction}
                className="hover:bg-bleu-light disabled:opacity-50 w-full sm:w-auto"
              >
                View Unique Errors
              </Button>
              {!isArchivedOnlyView && (
                <Button
                  onClick={handleArchiveByFilter}
                  style={{ backgroundColor: "var(--gris-primary)", color: "white" }}
                  disabled={totalResults === 0 || !!loadingAction}
                  className="hover:opacity-90 disabled:opacity-50 w-full sm:w-auto"
                >
                  {loadingAction === 'archive-all' && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                  Archive All Matching
                </Button>
              )}
              <Button
                onClick={handleRequeueByFilter}
                style={{ backgroundColor: "var(--bleu-primary)", color: "white" }}
                disabled={totalResults === 0 || !!loadingAction}
                className="hover:opacity-90 disabled:opacity-50 w-full sm:w-auto"
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

      {showCreateRuleModal && (
        <CreateRuleModal
          currentSearchTerm={searchTerm}
          currentFilters={getActiveFiltersPayload()}
          onClose={() => setShowCreateRuleModal(false)}
        />
      )}

      {showUniqueErrors && (
        <UniqueErrorsModal
          buckets={uniqueErrorBuckets}
          totalUnique={uniqueErrorTotal}
          loading={loadingUniqueErrors}
          onClose={() => setShowUniqueErrors(false)}
          onSelectError={handleSelectError}
        />
      )}
    </div>
  )
}