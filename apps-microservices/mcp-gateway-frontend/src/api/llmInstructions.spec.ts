import { describe, it, expect } from 'vitest'
import { llmInstructionsApi } from './llmInstructions'

describe('llmInstructionsApi', () => {
  it('exposes CRUD + usage methods', () => {
    expect(typeof llmInstructionsApi.list).toBe('function')
    expect(typeof llmInstructionsApi.get).toBe('function')
    expect(typeof llmInstructionsApi.create).toBe('function')
    expect(typeof llmInstructionsApi.update).toBe('function')
    expect(typeof llmInstructionsApi.remove).toBe('function')
    expect(typeof llmInstructionsApi.getUsage).toBe('function')
    expect(typeof llmInstructionsApi.getRendered).toBe('function')
  })
})
