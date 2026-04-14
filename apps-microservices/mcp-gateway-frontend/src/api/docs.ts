import { api } from './client'
import type { DocsServerSummary, DocsServerDetail } from '@/types/docs'

const BASE = '/api/v1/public'

export const docsApi = {
  list(): Promise<DocsServerSummary[]> {
    return api.get<DocsServerSummary[]>(`${BASE}/docs`)
  },

  get(slug: string): Promise<DocsServerDetail> {
    return api.get<DocsServerDetail>(`${BASE}/docs/${slug}`)
  },
}
