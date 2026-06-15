import { describe, it, expect } from 'vitest'
import * as usersApi from './users'

describe('users api', () => {
  it('exports the admin user actions', () => {
    expect(typeof usersApi.list).toBe('function')
    expect(typeof usersApi.promote).toBe('function')
    expect(typeof usersApi.demote).toBe('function')
    expect(typeof usersApi.block).toBe('function')
    expect(typeof usersApi.unblock).toBe('function')
    expect(typeof usersApi.revoke).toBe('function')
  })

  it('exports the MCP sync actions', () => {
    expect(typeof usersApi.syncMcp).toBe('function')
    expect(typeof usersApi.syncMcpAll).toBe('function')
  })
})
