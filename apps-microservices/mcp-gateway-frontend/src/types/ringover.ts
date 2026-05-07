// Ringover user/team types — mirror the JSON returned by the gateway proxy
// (GET /api/v1/ringover/users, GET /api/v1/ringover/teams). Ringover
// identifies users with numeric integer IDs (not UUIDs), so the filter shape
// carries `number[]` arrays rather than `string[]`.

export type RingoverFilterMode = 'none' | 'users' | 'teams' | 'creator' | 'self'

export interface RingoverFilter {
  mode: RingoverFilterMode
  user_ids?: number[]
  team_ids?: number[]
  // Set in responses only — the resolved Ringover user_id for the token's
  // creator (mode = 'creator'). Read-only on the frontend.
  creator_user_id?: number
}

export interface RingoverUser {
  user_id: number
  email?: string
  firstname?: string
  lastname?: string
  team_id?: number
  team_name?: string
}

export interface RingoverTeam {
  id: number
  name: string
}

export interface RingoverUsersResponse {
  users: RingoverUser[]
}

export interface RingoverTeamsResponse {
  teams: RingoverTeam[]
}
