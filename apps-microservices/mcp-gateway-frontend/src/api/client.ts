import { ApiError } from '@/types/api'
import { router } from '@/router'

const BASE_URL = import.meta.env.VITE_API_BASE_URL || ''

function getAuthToken(): string | null {
  return localStorage.getItem('auth_token')
}

async function request<T>(
  method: string,
  path: string,
  body?: unknown,
  params?: Record<string, string>
): Promise<T> {
  let url = `${BASE_URL}${path}`

  if (params) {
    const searchParams = new URLSearchParams(params)
    url += `?${searchParams.toString()}`
  }

  const headers: Record<string, string> = {}
  if (body !== undefined) {
    headers['Content-Type'] = 'application/json'
  }

  const token = getAuthToken()
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }

  const response = await fetch(url, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined
  })

  if (response.status === 401) {
    localStorage.removeItem('auth_token')
    router.push({ path: '/login', query: { redirect: window.location.pathname } })
    throw new ApiError(401, 'Unauthorized')
  }

  if (!response.ok) {
    const errorBody = await response.json().catch(() => undefined)
    throw new ApiError(response.status, response.statusText, errorBody)
  }

  if (response.status === 204) {
    return undefined as T
  }

  return response.json() as Promise<T>
}

// blobRequest is a bearer-authenticated GET that returns the raw response
// body as a Blob. Use this for file downloads where the caller wants to
// trigger a browser save-as — JSON parsing would corrupt binary payloads
// and defeat attachment Content-Disposition semantics.
async function blobRequest(path: string): Promise<Blob> {
  const url = `${BASE_URL}${path}`
  const headers: Record<string, string> = {}
  const token = getAuthToken()
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }
  const response = await fetch(url, { method: 'GET', headers })
  if (response.status === 401) {
    localStorage.removeItem('auth_token')
    router.push({ path: '/login', query: { redirect: window.location.pathname } })
    throw new ApiError(401, 'Unauthorized')
  }
  if (!response.ok) {
    const errorBody = await response.json().catch(() => undefined)
    throw new ApiError(response.status, response.statusText, errorBody)
  }
  return response.blob()
}

async function multipartRequest<T>(method: string, path: string, formData: FormData): Promise<T> {
  const url = `${BASE_URL}${path}`
  const headers: Record<string, string> = {}
  const token = getAuthToken()
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }
  // Deliberately no Content-Type — the browser sets the multipart boundary.

  const response = await fetch(url, { method, headers, body: formData })

  if (response.status === 401) {
    localStorage.removeItem('auth_token')
    router.push({ path: '/login', query: { redirect: window.location.pathname } })
    throw new ApiError(401, 'Unauthorized')
  }

  if (!response.ok) {
    const errorBody = await response.json().catch(() => undefined)
    throw new ApiError(response.status, response.statusText, errorBody)
  }

  if (response.status === 204) {
    return undefined as T
  }

  return response.json() as Promise<T>
}

export const api = {
  get<T>(path: string, params?: Record<string, string>): Promise<T> {
    return request<T>('GET', path, undefined, params)
  },
  post<T>(path: string, body?: unknown): Promise<T> {
    return request<T>('POST', path, body)
  },
  put<T>(path: string, body?: unknown): Promise<T> {
    return request<T>('PUT', path, body)
  },
  del<T>(path: string): Promise<T> {
    return request<T>('DELETE', path)
  },
  postMultipart<T>(path: string, formData: FormData): Promise<T> {
    return multipartRequest<T>('POST', path, formData)
  },
  getBlob(path: string): Promise<Blob> {
    return blobRequest(path)
  }
}
