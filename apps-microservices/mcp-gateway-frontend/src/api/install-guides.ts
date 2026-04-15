import { api } from './client'
import type { InstallExecutor, InstallConfig } from '@/types/install-guide'

// ── Public (no auth) ───────────────────────────────────────────────

export const installGuidesPublicApi = {
  listExecutors(): Promise<InstallExecutor[]> {
    return api.get<InstallExecutor[]>('/api/v1/public/install-guides/executors')
  },

  getExecutor(slug: string): Promise<InstallExecutor> {
    return api.get<InstallExecutor>(`/api/v1/public/install-guides/executors/${slug}`)
  },

  listConfigs(): Promise<InstallConfig[]> {
    return api.get<InstallConfig[]>('/api/v1/public/install-guides/configs')
  },

  getConfig(slug: string): Promise<InstallConfig> {
    return api.get<InstallConfig>(`/api/v1/public/install-guides/configs/${slug}`)
  },
}

// ── Admin (auth required) ──────────────────────────────────────────

export interface ExecutorListResponse {
  executors: InstallExecutor[]
  total: number
}

export interface ConfigListResponse {
  configs: InstallConfig[]
  total: number
}

export const installGuidesAdminApi = {
  // Executors
  listExecutors(): Promise<ExecutorListResponse> {
    return api.get<ExecutorListResponse>('/api/v1/install-guides/executors')
  },

  getExecutor(id: number): Promise<InstallExecutor> {
    return api.get<InstallExecutor>(`/api/v1/install-guides/executors/${id}`)
  },

  createExecutor(data: Partial<InstallExecutor>): Promise<InstallExecutor> {
    return api.post<InstallExecutor>('/api/v1/install-guides/executors', data)
  },

  updateExecutor(id: number, data: Partial<InstallExecutor>): Promise<InstallExecutor> {
    return api.put<InstallExecutor>(`/api/v1/install-guides/executors/${id}`, data)
  },

  deleteExecutor(id: number): Promise<void> {
    return api.del<void>(`/api/v1/install-guides/executors/${id}`)
  },

  // Configs
  listConfigs(): Promise<ConfigListResponse> {
    return api.get<ConfigListResponse>('/api/v1/install-guides/configs')
  },

  getConfig(id: number): Promise<InstallConfig> {
    return api.get<InstallConfig>(`/api/v1/install-guides/configs/${id}`)
  },

  createConfig(data: Partial<InstallConfig>): Promise<InstallConfig> {
    return api.post<InstallConfig>('/api/v1/install-guides/configs', data)
  },

  updateConfig(id: number, data: Partial<InstallConfig>): Promise<InstallConfig> {
    return api.put<InstallConfig>(`/api/v1/install-guides/configs/${id}`, data)
  },

  deleteConfig(id: number): Promise<void> {
    return api.del<void>(`/api/v1/install-guides/configs/${id}`)
  },
}
