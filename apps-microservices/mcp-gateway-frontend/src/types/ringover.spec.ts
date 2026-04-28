import { describe, it, expect } from 'vitest'
import type { RingoverFilter, RingoverUser, RingoverTeam } from './ringover'

describe('Ringover types', () => {
  it('RingoverFilter carries numeric id arrays', () => {
    const f: RingoverFilter = {
      mode: 'users',
      user_ids: [123, 456]
    }
    expect(f.user_ids?.[0]).toBe(123)
  })

  it('teams mode accepts team_ids', () => {
    const f: RingoverFilter = { mode: 'teams', team_ids: [7] }
    expect(f.team_ids?.length).toBe(1)
  })

  it('creator mode surfaces creator_user_id on responses', () => {
    const f: RingoverFilter = { mode: 'creator', creator_user_id: 42 }
    expect(f.creator_user_id).toBe(42)
  })

  it('RingoverUser/Team carry numeric identifiers', () => {
    const u: RingoverUser = { user_id: 1, team_id: 2, firstname: 'A' }
    const t: RingoverTeam = { id: 2, name: 'Sales' }
    expect(u.user_id + t.id).toBe(3)
  })
})
