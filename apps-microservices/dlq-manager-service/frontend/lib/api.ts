import axios from 'axios';

const api = axios.create({
    baseURL: '/api', // This will be proxied by Next.js dev server and served by FastAPI in production
});

// --- TYPE DEFINITIONS ---

export interface ServiceBucket {
    key: string;
    doc_count: number;
}

export interface ErrorBucket {
    key: string;
    doc_count: number;
}

export interface TimeBucket {
    key: string;
    key_as_string: string;
    doc_count: number;
}

export interface DashboardStats {
    pending_count: number;
    by_service: ServiceBucket[];
    by_error: ErrorBucket[];
    over_time: TimeBucket[];
}

export interface MessageSource {
    '@timestamp': string;
    service_name: string;
    error_reason: string;
    status?: 'Re-queued' | 'Re-queued (Edited)' | 'Archived' | 'Re-queued (Legacy)' | 'Auto-Archived';
    requeued_at?: string;
    original_payload: Record<string, any>;
    [key: string]: any; // Allow other fields
}

export interface Message {
    _id: string;
    _source: MessageSource;
}

export interface SearchResponse {
    messages: Message[];
    total: number;
}

export interface SearchParams {
    filters: Record<string, any>;
    searchTerm: string;
    page: number;
    pageSize: number;
}

export interface TaskResponse {
    status: string;
    message: string;
    task_id?: string;
}

export interface TaskStatusResponse {
    task_id: string;
    completed: boolean;
    status: string;
}

export interface AutoArchiveRule {
    _id?: string;
    name: string;
    description?: string;
    search_term?: string;
    filters?: Record<string, any>;
    is_active: boolean;
    created_at?: string;
    execution_count?: number;
    last_evaluated_at?: string;
    last_archived_at?: string;
}

export interface UniqueErrorBucket {
    service_name: string;
    error_reason: string;
    count: number;
}

export interface UniqueErrorsResponse {
    buckets: UniqueErrorBucket[];
    total_unique: number;
}

// --- API FUNCTIONS ---

export const apiGetDashboardStats = (filters?: { date_start?: string; date_end?: string }) => {
    return api.post<DashboardStats>('/dashboard-stats', filters || {});
};

export const apiGetServiceNames = (filters?: Record<string, any>) => {
    return api.post<{ services: ServiceBucket[] }>('/services', { filters: filters || {} });
};

export const apiSearchMessages = (searchParams: SearchParams) => {
    // Map frontend camelCase to backend snake_case
    const backendParams = {
        filters: searchParams.filters,
        search_term: searchParams.searchTerm,
        page: searchParams.page,
        page_size: searchParams.pageSize,
    };
    return api.post<SearchResponse>('/messages/search', backendParams);
};

export const apiGetMessageDetails = (messageId: string) => {
    return api.get<Message>(`/messages/${messageId}`);
};

export const apiRequeueMessage = (messageId: string) => {
    return api.post(`/messages/${messageId}/requeue`);
};

export const apiBulkRequeue = (messageIds: string[], rateLimit?: number) => {
    return api.post('/messages/bulk-requeue', { 
        message_ids: messageIds,
        rate_limit_per_second: rateLimit || null,
    });
};

export const apiBulkArchive = (messageIds: string[]) => {
    return api.post('/messages/bulk-archive', { message_ids: messageIds });
};

export const apiRequeueByFilter = (filters: Record<string, any>, searchTerm: string, rateLimit?: number) => {
    return api.post<TaskResponse>('/messages/requeue-by-filter', {
        filters,
        search_term: searchTerm,
        rate_limit_per_second: rateLimit || null,
    });
};

export const apiArchiveByFilter = (filters: Record<string, any>, searchTerm: string) => {
    return api.post<TaskResponse>('/messages/archive-by-filter', {
        filters,
        search_term: searchTerm,
    });
};

export const apiGetTaskStatus = (taskId: string) => {
    return api.get<TaskStatusResponse>(`/tasks/${taskId}`);
}

export const apiEditAndRequeueMessage = (messageId: string, newPayload: Record<string, any>) => {
    return api.put(`/messages/${messageId}/edit-and-requeue`, { new_payload: newPayload });
};

// Unique Errors
export const apiGetUniqueErrors = (filters: Record<string, any>, searchTerm: string) => {
    return api.post<UniqueErrorsResponse>('/messages/unique-errors', {
        filters,
        search_term: searchTerm,
    });
};

// Auto-Archive Rules
export const apiGetRules = () => {
    return api.get<AutoArchiveRule[]>('/rules');
};

export const apiCreateRule = (rule: AutoArchiveRule) => {
    return api.post<{status: string, rule_id: string}>('/rules', rule);
};

export const apiToggleRule = (ruleId: string, isActive: boolean) => {
    return api.patch(`/rules/${ruleId}/toggle`, { is_active: isActive });
};

export const apiDeleteRule = (ruleId: string) => {
    return api.delete(`/rules/${ruleId}`);
};

