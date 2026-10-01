import { api } from './client'
import { ApiError } from '@/types/api'
import type { SlackStatus, SlackTestResponse } from '@/types/slack'

const BASE = '/api/v1/slack'

export const slackApi = {
  getStatus(): Promise<SlackStatus> {
    return api.get<SlackStatus>(`${BASE}/status`)
  },

  // sendTest returns a success/failure payload. The backend uses non-2xx
  // responses (503 disabled, 502 delivery error) to distinguish from a true
  // success, so we translate ApiError back into a structured response the UI
  // can render uniformly instead of branching on try/catch.
  async sendTest(): Promise<SlackTestResponse> {
    try {
      return await api.post<SlackTestResponse>(`${BASE}/test`, undefined)
    } catch (err) {
      if (err instanceof ApiError) {
        const body = err.body as SlackTestResponse | undefined
        if (body && body.status && body.message) {
          return body
        }
        return { status: 'error', message: err.message || 'Unknown error' }
      }
      throw err
    }
  }
}
