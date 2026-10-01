# hellopro-auth

Framework-free account-service OAuth 2.1 + PKCE login core for Python services
(config, oauth, session, flow). Mirror of the node `@hellopro/auth` lib.
Credential resolution reuses `common_utils.sso`.

## Consume
`pip install -e libs/common-utils libs/auth/python`, then
`from hellopro_auth import get_auth_config, start_login, complete_callback, read_session, SESSION_COOKIE`.
Keep your own FastAPI route handlers.
