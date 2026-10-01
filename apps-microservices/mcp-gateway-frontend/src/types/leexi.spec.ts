import { describe, it, expect } from 'vitest'
import type { LeexiFilter, LeexiUser, LeexiTeam } from './leexi'

describe('Leexi types', () => {
  it('LeexiFilter carries uuid arrays in users mode', () => {
    const f: LeexiFilter = {
      mode: 'users',
      user_uuids: ['uuid-1', 'uuid-2']
    }
    expect(f.user_uuids?.[0]).toBe('uuid-1')
  })

  it('teams mode accepts team_uuids', () => {
    const f: LeexiFilter = { mode: 'teams', team_uuids: ['team-uuid'] }
    expect(f.team_uuids?.length).toBe(1)
  })

  it('creator mode surfaces creator_uuid on responses', () => {
    const f: LeexiFilter = { mode: 'creator', creator_uuid: 'creator-uuid' }
    expect(f.creator_uuid).toBe('creator-uuid')
  })

  it("self mode resolves at request time and carries no UUID/ID fields", () => {
    const f: LeexiFilter = { mode: 'self' }
    expect(f.mode).toBe('self')
    expect(f.user_uuids).toBeUndefined()
    expect(f.team_uuids).toBeUndefined()
  })

  it('LeexiUser/Team carry string identifiers', () => {
    const u: LeexiUser = { uuid: 'u1', team_uuid: 't1', first_name: 'A' }
    const t: LeexiTeam = { uuid: 't1', name: 'Sales' }
    expect(u.team_uuid).toBe(t.uuid)
  })
})
