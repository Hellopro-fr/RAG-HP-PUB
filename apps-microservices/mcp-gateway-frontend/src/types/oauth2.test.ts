// Type-only smoke test for src/types/oauth2.ts
// Frontend type files have no runtime — this asserts the module imports
// cleanly and compiles. Replace with proper tests when a test runner is set up.
import type { OAuth2Client, CreateOAuth2ClientRequest } from './oauth2'

const _client: OAuth2Client = {
  id: '',
  name: '',
  secret_prefix: '',
  server_ids: [],
  server_tools: [],
  access_token_ttl: 0,
  is_active: true,
  created_at: '',
  updated_at: '',
  dynamically_registered: false,
}
void _client

const _req: CreateOAuth2ClientRequest = {
  name: '',
  server_ids: [],
}
void _req
