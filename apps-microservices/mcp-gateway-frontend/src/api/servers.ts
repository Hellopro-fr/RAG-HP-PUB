import { api } from './client'
import type {
  Server,
  ServerDetail,
  ServerListResponse,
  CreateServerRequest,
  UpdateServerRequest,
  ImportResult
} from '@/types/server'

const BASE = '/api/v1'

export interface ServerListFilters {
  is_active?: boolean
  tag?: string
  created_by?: string
  exclude_templates?: boolean
  /**
   * Drop the per-caller ownership filter so non-admin users see every active
   * server. Set this when the list feeds a scope picker (token / OAuth2
   * creation form) — the secret-bearing fields are already redacted in the
   * list DTO, so this only widens what the picker can offer, not what the
   * caller can mutate.
   */
  include_all?: boolean
}

function serializeFilters(filters?: ServerListFilters): Record<string, string> | undefined {
  if (!filters) return undefined
  const out: Record<string, string> = {}
  for (const [k, v] of Object.entries(filters)) {
    if (v === undefined) continue
    out[k] = typeof v === 'boolean' ? String(v) : v
  }
  return out
}

export const serversApi = {
  list(params?: ServerListFilters): Promise<ServerListResponse> {
    return api.get<ServerListResponse>(`${BASE}/servers`, serializeFilters(params))
  },

  get(id: string): Promise<ServerDetail> {
    return api.get<ServerDetail>(`${BASE}/servers/${id}`)
  },

  create(data: CreateServerRequest): Promise<Server> {
    return api.post<Server>(`${BASE}/servers`, data)
  },

  update(id: string, data: UpdateServerRequest): Promise<Server> {
    return api.put<Server>(`${BASE}/servers/${id}`, data)
  },

  delete(id: string): Promise<void> {
    return api.del<void>(`${BASE}/servers/${id}`)
  },

  enable(id: string): Promise<void> {
    return api.post<void>(`${BASE}/servers/${id}/enable`)
  },

  disable(id: string): Promise<void> {
    return api.post<void>(`${BASE}/servers/${id}/disable`)
  },

  discover(id: string): Promise<ServerDetail> {
    return api.post<ServerDetail>(`${BASE}/servers/${id}/discover`)
  },

  discoverAll(): Promise<void> {
    return api.post<void>(`${BASE}/servers/discover-all`)
  },

  enableTool(serverId: string, toolName: string): Promise<void> {
    return api.post<void>(`${BASE}/servers/${serverId}/tools/${toolName}/enable`)
  },

  disableTool(serverId: string, toolName: string): Promise<void> {
    return api.post<void>(`${BASE}/servers/${serverId}/tools/${toolName}/disable`)
  },

  import(json: unknown, autoDiscover?: boolean): Promise<ImportResult> {
    return api.post<ImportResult>(`${BASE}/servers/import`, { config: json, auto_discover: autoDiscover })
  },

  async listTags(): Promise<string[]> {
    const response = await api.get<{ tags: string[] }>(`${BASE}/tags`)
    return response.tags || []
  },

  listTools(): Promise<unknown[]> {
    return api.get<unknown[]>(`${BASE}/tools`)
  },

  async listIcons(): Promise<string[]> {
    const response = await api.get<{ icons: string[] }>(`${BASE}/server-icons`)
    return response.icons || []
  },

  async uploadIcon(file: File): Promise<string> {
    const formData = new FormData()
    formData.append('icon', file)

    const url = `${BASE}/server-icons`
    const headers: Record<string, string> = {}
    const token = localStorage.getItem('auth_token')
    if (token) {
      headers['Authorization'] = `Bearer ${token}`
    }

    const response = await fetch(url, {
      method: 'POST',
      headers,
      body: formData
    })

    if (!response.ok) {
      const errorBody = await response.json().catch(() => undefined)
      throw new Error(errorBody?.error || 'Failed to upload icon')
    }

    const result = await response.json()
    return result.icon
  }
}
