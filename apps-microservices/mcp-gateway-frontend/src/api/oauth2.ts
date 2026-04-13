import { api } from './client'
import type {
  OAuth2Client,
  OAuth2ClientListResponse,
  CreateOAuth2ClientRequest,
  UpdateOAuth2ClientRequest
} from '@/types/oauth2'

const BASE = '/api/v1'

export const oauth2Api = {
  list(): Promise<OAuth2ClientListResponse> {
    return api.get<OAuth2ClientListResponse>(`${BASE}/oauth2/clients`)
  },

  get(id: string): Promise<OAuth2Client> {
    return api.get<OAuth2Client>(`${BASE}/oauth2/clients/${id}`)
  },

  create(data: CreateOAuth2ClientRequest): Promise<OAuth2Client> {
    return api.post<OAuth2Client>(`${BASE}/oauth2/clients`, data)
  },

  update(id: string, data: UpdateOAuth2ClientRequest): Promise<OAuth2Client> {
    return api.put<OAuth2Client>(`${BASE}/oauth2/clients/${id}`, data)
  },

  delete(id: string): Promise<void> {
    return api.del<void>(`${BASE}/oauth2/clients/${id}`)
  },

  revoke(id: string): Promise<void> {
    return api.post<void>(`${BASE}/oauth2/clients/${id}/revoke`)
  }
}
