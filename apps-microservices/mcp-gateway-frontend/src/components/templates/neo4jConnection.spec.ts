import { describe, it, expect } from 'vitest'
import {
  appendNeo4jFields,
  emptyNeo4jConnection,
  isNeo4jTemplate,
  isReadOnly,
  readOnlyExtraEnv,
  validateNeo4jConnection
} from './neo4jConnection'

const ok = { uri: 'bolt://neo4j:7687', username: 'reader', password: 's3cret', database: 'neo4j' }

describe('neo4jConnection', () => {
  it('detects Neo4j templates by runner', () => {
    expect(isNeo4jTemplate({ runner: 'neo4j' })).toBe(true)
    expect(isNeo4jTemplate({ runner: 'google' })).toBe(false)
    expect(isNeo4jTemplate({})).toBe(false)
    expect(isNeo4jTemplate(null)).toBe(false)
  })

  it('starts empty with the default database', () => {
    expect(emptyNeo4jConnection()).toEqual({ uri: '', username: '', password: '', database: 'neo4j' })
  })

  it('accepts every supported scheme', () => {
    for (const uri of ['bolt://h:7687', 'bolt+s://h', 'bolt+ssc://h', 'neo4j://h', 'neo4j+s://h.example.com', 'neo4j+ssc://10.0.0.1:7687']) {
      expect(validateNeo4jConnection({ ...ok, uri })).toBeNull()
    }
  })

  it('rejects invalid input with a French message', () => {
    expect(validateNeo4jConnection({ ...ok, uri: '' })).toBe("L'URI est obligatoire")
    expect(validateNeo4jConnection({ ...ok, uri: 'http://h:7474' })).toMatch(/^Schéma attendu/)
    expect(validateNeo4jConnection({ ...ok, uri: 'bolt://neo4j:pw@h' })).toBe("Ne mettez pas d'identifiants dans l'URI")
    expect(validateNeo4jConnection({ ...ok, uri: 'pas une uri' })).toBe('URI invalide')
    expect(validateNeo4jConnection({ ...ok, username: ' ' })).toBe("L'utilisateur est obligatoire")
    expect(validateNeo4jConnection({ ...ok, password: '  ' })).toBe('Le mot de passe est obligatoire')
    expect(validateNeo4jConnection({ ...ok, database: 'a b' })).toMatch(/^Nom de base invalide/)
    expect(validateNeo4jConnection({ ...ok, database: '' })).toBeNull()
  })

  it('writes the multipart fields the gateway reads', () => {
    const fd = new FormData()
    appendNeo4jFields(fd, { uri: ' bolt://neo4j:7687 ', username: ' reader ', password: ' p w ', database: '' })
    expect(fd.get('neo4j_uri')).toBe('bolt://neo4j:7687')
    expect(fd.get('neo4j_username')).toBe('reader')
    expect(fd.get('neo4j_password')).toBe(' p w ')
    expect(fd.get('neo4j_database')).toBe('neo4j')
  })

  it('maps the read-only checkbox to extra_env and back', () => {
    expect(readOnlyExtraEnv(true)).toEqual({ NEO4J_READ_ONLY: 'true' })
    expect(readOnlyExtraEnv(false)).toEqual({ NEO4J_READ_ONLY: 'false' })
    expect(isReadOnly({ NEO4J_READ_ONLY: 'false' })).toBe(false)
    expect(isReadOnly({ NEO4J_READ_ONLY: 'true' })).toBe(true)
    expect(isReadOnly(undefined)).toBe(true) // template default is read-only
  })
})
