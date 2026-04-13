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

export const serversApi = {
  list(params?: { is_active?: string; tag?: string; created_by?: string }): Promise<ServerListResponse> {
    return api.get<ServerListResponse>(`${BASE}/servers`, params as Record<string, string>)
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
  }
}
