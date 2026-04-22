import { api } from './client'
import type { User } from '@/types/user'

const BASE = '/api/v1'

export interface UserListResponse {
  users: User[]
}

export const usersApi = {
  list(role?: string): Promise<UserListResponse> {
    const params: Record<string, string> = {}
    if (role) params.role = role
    return api.get<UserListResponse>(`${BASE}/users`, Object.keys(params).length ? params : undefined)
  },

  update(id: number, role: string): Promise<void> {
    return api.put<void>(`${BASE}/users/${id}`, { role })
  },

  toggleAllowed(id: number, isAllowed: boolean): Promise<User> {
    return api.post<User>(`${BASE}/users/${id}/toggle-allowed`, { is_allowed: isAllowed })
  },

  delete(id: number): Promise<void> {
    return api.del<void>(`${BASE}/users/${id}`)
  }
}
