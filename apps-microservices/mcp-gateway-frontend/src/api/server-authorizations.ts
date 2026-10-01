import { api } from './client'
import type {
  ServerAuthorization,
  CreateServerAuthorizationRequest,
} from '@/types/server-authorization'

const BASE = '/api/v1'

export const serverAuthorizationsApi = {
  list(serverID?: string): Promise<ServerAuthorization[]> {
    const params = serverID ? { server_id: serverID } : undefined
    return api.get<ServerAuthorization[]>(`${BASE}/server-authorizations`, params)
  },

  create(data: CreateServerAuthorizationRequest): Promise<ServerAuthorization> {
    return api.post<ServerAuthorization>(`${BASE}/server-authorizations`, data)
  },

  delete(serverID: string, email: string): Promise<void> {
    const sid = encodeURIComponent(serverID)
    const e = encodeURIComponent(email)
    return api.del<void>(`${BASE}/server-authorizations/${sid}/${e}`)
  },
}
