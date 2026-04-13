import { api } from './client'
import type {
  AuthorizeInfo,
  AuthorizeLoginRequest,
  AuthorizeLoginResponse,
  AuthorizeConsentRequest,
  AuthorizeConsentResponse
} from '@/types/oauth2'

const BASE = '/api/v1/oauth2/authorize'

export const authorizeApi = {
  getInfo(clientId: string, redirectUri: string): Promise<AuthorizeInfo> {
    return api.get<AuthorizeInfo>(`${BASE}/info`, {
      client_id: clientId,
      redirect_uri: redirectUri
    })
  },

  login(data: AuthorizeLoginRequest): Promise<AuthorizeLoginResponse> {
    return api.post<AuthorizeLoginResponse>(`${BASE}/login`, data)
  },

  consent(data: AuthorizeConsentRequest): Promise<AuthorizeConsentResponse> {
    return api.post<AuthorizeConsentResponse>(`${BASE}/consent`, data)
  }
}
