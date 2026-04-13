import { api } from './client'
import type {
  LeexiUsersResponse,
  LeexiTeamsResponse
} from '@/types/leexi'

const BASE = '/api/v1/leexi'

// leexiApi wraps the gateway's Leexi proxy endpoints. Both calls return 503
// when the gateway has no Leexi credentials configured — callers should
// surface a friendly disabled state in that case.
export const leexiApi = {
  listUsers(): Promise<LeexiUsersResponse> {
    return api.get<LeexiUsersResponse>(`${BASE}/users`)
  },

  listTeams(): Promise<LeexiTeamsResponse> {
    return api.get<LeexiTeamsResponse>(`${BASE}/teams`)
  }
}
