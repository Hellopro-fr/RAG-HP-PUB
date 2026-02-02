// ========================================
// API CLIENT - HTTP REQUEST HANDLER
// ========================================

import type { ApiResponse } from '@/types';

interface RequestOptions extends RequestInit {
  timeout?: number;
}

// Default request timeout (30 seconds)
const DEFAULT_TIMEOUT = 30000;

/**
 * Generic API client for making HTTP requests
 * Compatible with both server and client components in Next.js
 */
export async function apiClient<T>(
  url: string,
  options: RequestOptions = {}
): Promise<ApiResponse<T>> {
  const { timeout = DEFAULT_TIMEOUT, ...fetchOptions } = options;

  // Create abort controller for timeout
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeout);

  try {
    const response = await fetch(url, {
      ...fetchOptions,
      signal: controller.signal,
      headers: {
        'Content-Type': 'application/json',
        ...fetchOptions.headers,
      },
    });

    clearTimeout(timeoutId);

    // Parse response
    let data: T | null = null;
    try {
      data = await response.json();
    } catch {
      // Response might not be JSON
      data = null;
    }

    if (!response.ok) {
      return {
        data: null,
        error: data ? String((data as Record<string, unknown>).message || 'Request failed') : `HTTP ${response.status}`,
        status: response.status,
      };
    }

    return {
      data,
      error: null,
      status: response.status,
    };
  } catch (error) {
    clearTimeout(timeoutId);

    if (error instanceof Error) {
      if (error.name === 'AbortError') {
        return {
          data: null,
          error: 'Request timeout',
          status: 408,
        };
      }
      return {
        data: null,
        error: error.message,
        status: 500,
      };
    }

    return {
      data: null,
      error: 'Unknown error occurred',
      status: 500,
    };
  }
}

/**
 * GET request helper
 */
export function get<T>(url: string, options?: RequestOptions): Promise<ApiResponse<T>> {
  return apiClient<T>(url, { ...options, method: 'GET' });
}

/**
 * POST request helper
 */
export function post<T>(url: string, body: unknown, options?: RequestOptions): Promise<ApiResponse<T>> {
  return apiClient<T>(url, {
    ...options,
    method: 'POST',
    body: JSON.stringify(body),
  });
}

/**
 * PUT request helper
 */
export function put<T>(url: string, body: unknown, options?: RequestOptions): Promise<ApiResponse<T>> {
  return apiClient<T>(url, {
    ...options,
    method: 'PUT',
    body: JSON.stringify(body),
  });
}

/**
 * DELETE request helper
 */
export function del<T>(url: string, options?: RequestOptions): Promise<ApiResponse<T>> {
  return apiClient<T>(url, { ...options, method: 'DELETE' });
}
