// Type-only smoke test — server-authorization.ts has no runtime, this
// asserts the module compiles. Excluded from production build via
// tsconfig.app.json.
import type {
  ServerAuthorization,
  CreateServerAuthorizationRequest,
} from './server-authorization'

const _g: ServerAuthorization = {
  server_id: '',
  email: '',
  created_at: '',
}
const _r: CreateServerAuthorizationRequest = { server_id: '', email: '' }
void _g
void _r

describe.skip('server-authorization types', () => {
  it('compiles', () => {
    expect(true).toBe(true)
  })
})
