// Neo4j template helpers (runner = 'neo4j'). The gateway validates again
// (validation.ValidateNeo4jCredentials) and stays the source of truth; this
// only gives the admin immediate feedback.

export interface Neo4jConnectionInput {
  uri: string
  username: string
  password: string
  database: string
}

const SCHEMES = ['bolt:', 'bolt+s:', 'bolt+ssc:', 'neo4j:', 'neo4j+s:', 'neo4j+ssc:']
const DATABASE_RE = /^[A-Za-z0-9._-]{1,63}$/

export function isNeo4jTemplate(t: { runner?: string } | null | undefined): boolean {
  return t?.runner === 'neo4j'
}

export function emptyNeo4jConnection(): Neo4jConnectionInput {
  return { uri: '', username: '', password: '', database: 'neo4j' }
}

export function validateNeo4jConnection(c: Neo4jConnectionInput): string | null {
  const uri = c.uri.trim()
  if (!uri) return "L'URI est obligatoire"
  let parsed: URL
  try {
    parsed = new URL(uri)
  } catch {
    return 'URI invalide'
  }
  if (!SCHEMES.includes(parsed.protocol.toLowerCase())) {
    return 'Schéma attendu : bolt, bolt+s, bolt+ssc, neo4j, neo4j+s ou neo4j+ssc'
  }
  if (parsed.username || parsed.password) return "Ne mettez pas d'identifiants dans l'URI"
  if (!parsed.hostname) return "L'URI doit contenir un hôte"
  if (!c.username.trim()) return "L'utilisateur est obligatoire"
  if (!c.password.trim()) return 'Le mot de passe est obligatoire'
  const database = c.database.trim() || 'neo4j'
  if (!DATABASE_RE.test(database)) return 'Nom de base invalide (lettres, chiffres, . _ -)'
  return null
}

// Multipart field names read by the gateway's credentialsFromRequest.
// The password is sent as typed (never trimmed).
export function appendNeo4jFields(fd: FormData, c: Neo4jConnectionInput): void {
  fd.append('neo4j_uri', c.uri.trim())
  fd.append('neo4j_username', c.username.trim())
  fd.append('neo4j_password', c.password)
  fd.append('neo4j_database', c.database.trim() || 'neo4j')
}

export function readOnlyExtraEnv(readOnly: boolean): Record<string, string> {
  return { NEO4J_READ_ONLY: readOnly ? 'true' : 'false' }
}

// Missing value = template default, which is read-only.
export function isReadOnly(extraEnv: Record<string, string> | null | undefined): boolean {
  return extraEnv?.NEO4J_READ_ONLY !== 'false'
}
