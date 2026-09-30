import { api } from './client'
import type {
  Template,
  TemplateExportRow,
  TemplateInstance,
  TemplateListResponse,
  TemplateInstanceListResponse,
  CreateInstanceParams,
  RotateNeo4jParams
} from '@/types/templates'
import { appendNeo4jFields } from '@/components/templates/neo4jConnection'

const BASE = '/api/v1'

export const templatesApi = {
  list(): Promise<TemplateListResponse> {
    return api.get<TemplateListResponse>(`${BASE}/templates`)
  },

  // Creates ONE template (admin-only, insert-only). 409 when the slug exists.
  create(row: TemplateExportRow): Promise<Template> {
    return api.post<Template>(`${BASE}/templates`, row)
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
    if (params.neo4j) {
      appendNeo4jFields(formData, params.neo4j)
    } else if (params.credentials) {
      formData.append('credentials', params.credentials)
    }
    if (params.tags && params.tags.length > 0) {
      formData.append('tags', JSON.stringify(params.tags))
    }
    if (params.icon) {
      formData.append('icon', params.icon)
    }
    if (params.tool_prefix) {
      formData.append('tool_prefix', params.tool_prefix)
    }
    if (params.auto_discover !== undefined) {
      formData.append('auto_discover', params.auto_discover ? 'true' : 'false')
    }
    return api.postMultipart<TemplateInstance>(`${BASE}/template-instances`, formData)
  },

  restart(id: string): Promise<void> {
    return api.post<void>(`${BASE}/template-instances/${id}/restart`)
  },

  rotate(id: string, payload: File | RotateNeo4jParams): Promise<void> {
    const formData = new FormData()
    if (payload instanceof File) {
      formData.append('credentials', payload)
    } else {
      appendNeo4jFields(formData, payload.neo4j)
      if (payload.extra_env) {
        formData.append('extra_env', JSON.stringify(payload.extra_env))
      }
    }
    return api.postMultipart<void>(`${BASE}/template-instances/${id}/rotate-credentials`, formData)
  },

  delete(id: string): Promise<void> {
    return api.del<void>(`${BASE}/template-instances/${id}`)
  },

  // exportCatalog downloads the full template catalog as a JSON blob. The
  // caller is responsible for saving the blob via URL.createObjectURL — this
  // keeps the module free of DOM side effects and makes the helper reusable
  // from any component.
  exportCatalog(): Promise<Blob> {
    return api.getBlob(`${BASE}/templates/export`)
  },

  // importCatalog reads the file client-side, parses it into the export
  // envelope shape, and POSTs the decoded object to the backend. Parsing up
  // front surfaces malformed JSON with a readable error before a round-trip.
  async importCatalog(file: File): Promise<{ imported: number }> {
    const text = await file.text()
    let payload: unknown
    try {
      payload = JSON.parse(text)
    } catch {
      throw new Error('Fichier JSON invalide')
    }
    return api.post<{ imported: number }>(`${BASE}/templates/import`, payload)
  }
}
