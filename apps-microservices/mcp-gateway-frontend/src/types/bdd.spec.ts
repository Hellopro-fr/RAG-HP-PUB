import { describe, it, expect } from 'vitest'
import { HELLOPRO_DATABASES } from './bdd'

describe('HELLOPRO_DATABASES', () => {
  it('exposes the three Hellopro databases with stable ids', () => {
    expect(HELLOPRO_DATABASES.map((d) => d.id)).toEqual([1, 5, 10])
  })

  it('exposes the expected slugs', () => {
    expect(HELLOPRO_DATABASES.map((d) => d.slug)).toEqual(['bo', 'data', 'ia'])
  })
})
