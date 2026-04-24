import { api } from './client'
import type {
  RingoverUsersResponse,
  RingoverTeamsResponse
} from '@/types/ringover'

const BASE = '/api/v1/ringover'

// ringoverApi wraps the gateway's Ringover proxy endpoints. Both calls return
// 503 when the gateway has no Ringover credentials configured — callers
// should surface a friendly disabled state in that case.
export const ringoverApi = {
  listUsers(): Promise<RingoverUsersResponse> {
    return api.get<RingoverUsersResponse>(`${BASE}/users`)
  },

  listTeams(): Promise<RingoverTeamsResponse> {
    return api.get<RingoverTeamsResponse>(`${BASE}/teams`)
  }
}
