import { describe, it, expect } from 'vitest'
import type {
  LLMInstruction,
  CreateLLMInstructionRequest,
  LLMInstructionRow
} from './llmInstruction'

describe('LLMInstruction types', () => {
  it('accepts both per_server and general row kinds', () => {
    const req: CreateLLMInstructionRequest = {
      title: 'My page',
      description: 'admin note',
      rows: [
        { kind: 'general', title: 'Boilerplate', body: 'Always do X.', server_ids: [] },
        { kind: 'per_server', title: 'R1', body: 'Prefer search_*', server_ids: ['s1'] }
      ]
    }
    expect(req.rows[0]?.kind).toBe('general')
    expect(req.rows[1]?.kind).toBe('per_server')
  })

  it('serialises LLMInstruction to JSON and back', () => {
    const row: LLMInstructionRow = { id: 'r1', kind: 'general', body: 'b', server_ids: [] }
    const ins: LLMInstruction = {
      id: 'abc',
      title: 'T',
      rows: [row],
      created_at: '2026-04-23T00:00:00Z',
      updated_at: '2026-04-23T00:00:00Z'
    }
    const round = JSON.parse(JSON.stringify(ins)) as LLMInstruction
    expect(round.id).toBe('abc')
    expect(round.rows[0]?.kind).toBe('general')
  })
})
