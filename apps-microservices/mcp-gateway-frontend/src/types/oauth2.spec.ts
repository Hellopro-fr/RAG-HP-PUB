import { describe, it, expect } from 'vitest'
import type { CreateOAuth2ClientRequest } from './oauth2'

describe('OAuth2 types', () => {
  it('accepts instruction_ids on CreateOAuth2ClientRequest', () => {
    const req: CreateOAuth2ClientRequest = {
      name: 'c',
      server_ids: ['s1'],
      instruction_ids: ['i1']
    }
    expect(req.instruction_ids?.[0]).toBe('i1')
  })
})
