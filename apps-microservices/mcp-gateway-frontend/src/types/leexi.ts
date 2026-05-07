// Leexi user/team types — mirror the JSON returned by the gateway proxy
// (GET /api/v1/leexi/users, GET /api/v1/leexi/teams). These shapes are also
// used by the per-token Leexi ownership filter UI.

export type LeexiFilterMode = 'none' | 'users' | 'teams' | 'creator' | 'self'

export interface LeexiFilter {
  mode: LeexiFilterMode
  user_uuids?: string[]
  team_uuids?: string[]
  // Set in responses only — the resolved Leexi user UUID for the token's
  // creator (mode = 'creator'). Read-only on the frontend.
  creator_uuid?: string
}

export interface LeexiUser {
  uuid: string
  email?: string
  first_name?: string
  last_name?: string
  team_uuid?: string
  team_name?: string
}

export interface LeexiTeam {
  uuid: string
  name: string
}

export interface LeexiUsersResponse {
  users: LeexiUser[]
}

export interface LeexiTeamsResponse {
  teams: LeexiTeam[]
}
