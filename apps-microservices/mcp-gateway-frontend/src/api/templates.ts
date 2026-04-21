import { api } from './client'
import { ApiError } from '@/types/api'
import type {
  Template,
  TemplateInstance,
  TemplateListResponse,
  TemplateInstanceListResponse,
  CreateInstanceParams
} from '@/types/templates'

const BASE = '/api/v1'

function authHeaders(): Record<string, string> {
  const headers: Record<string, string> = {}
  const token = localStorage.getItem('auth_token')
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }
  return headers
}

async function multipartRequest<T>(url: string, formData: FormData): Promise<T> {
  const response = await fetch(url, {
    method: 'POST',
    headers: authHeaders(),
    body: formData
  })
  if (!response.ok) {
    const errorBody = await response.json().catch(() => undefined)
    throw new ApiError(response.status, response.statusText, errorBody)
  }
  if (response.status === 204) {
    return undefined as T
  }
  return response.json() as Promise<T>
}

export const templatesApi = {
  list(): Promise<TemplateListResponse> {
    return api.get<TemplateListResponse>(`${BASE}/templates`)
  },

  get(slug: string): Promise<Template> {
    return api.get<Template>(`${BASE}/templates/${slug}`)
  },

  listInstances(slug?: string): Promise<TemplateInstanceListResponse> {
    const params = slug ? { template_slug: slug } : undefined
    return api.get<TemplateInstanceListResponse>(`${BASE}/template-instances`, params)
  },

  getInstance(id: string): Promise<TemplateInstance> {
    return api.get<TemplateInstance>(`${BASE}/template-instances/${id}`)
  },

  createInstance(params: CreateInstanceParams): Promise<TemplateInstance> {
    const formData = new FormData()
    formData.append('template_slug', params.template_slug)
    formData.append('name', params.name)
    if (params.extra_env) {
      formData.append('extra_env', JSON.stringify(params.extra_env))
    }
    formData.append('credentials', params.credentials)
    return multipartRequest<TemplateInstance>(`${BASE}/template-instances`, formData)
  },

  restart(id: string): Promise<void> {
    return api.post<void>(`${BASE}/template-instances/${id}/restart`)
  },

  rotate(id: string, credentials: File): Promise<void> {
    const formData = new FormData()
    formData.append('credentials', credentials)
    return multipartRequest<void>(`${BASE}/template-instances/${id}/rotate-credentials`, formData)
  },

  delete(id: string): Promise<void> {
    return api.del<void>(`${BASE}/template-instances/${id}`)
  }
}
