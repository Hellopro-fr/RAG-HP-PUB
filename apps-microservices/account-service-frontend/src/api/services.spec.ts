import { describe, it, expect } from 'vitest'
import * as servicesApi from './services'

describe('services api', () => {
  it('exports list, get, create, update, remove, rotateSecret, testWebhook', () => {
    expect(typeof servicesApi.list).toBe('function')
    expect(typeof servicesApi.get).toBe('function')
    expect(typeof servicesApi.create).toBe('function')
    expect(typeof servicesApi.update).toBe('function')
    expect(typeof servicesApi.remove).toBe('function')
    expect(typeof servicesApi.rotateSecret).toBe('function')
    expect(typeof servicesApi.testWebhook).toBe('function')
  })
})
