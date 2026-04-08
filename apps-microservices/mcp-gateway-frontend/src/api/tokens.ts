import { api } from './client'
import type {
  ScopeToken,
  TokenListResponse,
  CreateTokenRequest,
  UpdateTokenRequest
} from '@/types/token'

const BASE = '/api/v1'

export const tokensApi = {
  list(): Promise<TokenListResponse> {
    return api.get<TokenListResponse>(`${BASE}/tokens`)
  },

  get(id: string): Promise<ScopeToken> {
    return api.get<ScopeToken>(`${BASE}/tokens/${id}`)
  },

  create(data: CreateTokenRequest): Promise<ScopeToken> {
    return api.post<ScopeToken>(`${BASE}/tokens`, data)
  },

  update(id: string, data: UpdateTokenRequest): Promise<ScopeToken> {
    return api.put<ScopeToken>(`${BASE}/tokens/${id}`, data)
  },

  delete(id: string): Promise<void> {
    return api.del<void>(`${BASE}/tokens/${id}`)
  },

  revoke(id: string): Promise<void> {
    return api.post<void>(`${BASE}/tokens/${id}/revoke`)
  }
}
