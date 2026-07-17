# AuthorizeView consent UX port from `public/consent-page/`

**Date:** 2026-05-19
**Author:** sandrianirinaharivelo@hellopro.fr
**Status:** Draft

## Goal

Port the visual layout and UX of `public/consent-page/` (Next.js / React 19 / shadcn mockup)
into `apps-microservices/mcp-gateway-frontend/src/views/AuthorizeView.vue` (Vue 3 /
radix-vue / Tailwind 4). The OAuth2 flow logic — `authorizeApi.getInfo` / `consent`
/ deny redirect — stays exactly as it is; only the presentation layer changes, plus
two functional adjustments captured below.

## Non-goals

- No backend changes to `mcp-gateway-service`. The `AuthorizeServer` / `AuthorizeInfo`
  payload shape is unchanged.
- No new fields on the Go OAuth2 authorize server (`riskLevel`, `sensitive` scopes,
  `dataAccess`, `serverUrl` from the mockup are dropped, not added).
- No change to the standalone `LoginView.vue` or to the server-rendered HTML
  `/authorize` endpoint in `internal/authserver/authorize.go`.

## Background

### Existing AuthorizeView

`src/views/AuthorizeView.vue` already implements the real OAuth2 consent flow:

- Reads `client_id`, `redirect_uri`, `code_challenge`, `code_challenge_method`,
  `state` from the route query.
- `fetchInfo()` calls `GET /api/v1/oauth2/authorize/info` via `authorizeApi.getInfo`
  and assigns `clientName`, `servers`, `csrfToken`, `preConfigured`.
- Renders three branches: `loading`, `fatalError`, and either `step === 'login'` or
  `step === 'consent'`. **The login branch is unreachable**: `fetchInfo` always sets
  `step.value = 'consent'` (`AuthorizeView.vue:358`).
- Per-tool selection state in `selectedTools: Map<string, Set<string>>` with derived
  `selectedServerIds` and `selectedToolIds` computeds.
- `handleConsent` POSTs to `/consent` and follows `response.redirect_url`.
- `handleDeny` builds an `error=access_denied` redirect to `redirect_uri`.

### Existing consent-page mockup

`public/consent-page/` is a Next.js mockup with hardcoded MCP servers
(`Linear`, `Notion`, `Slack`, …) and richer per-server metadata that has **no
equivalent in the backend payload**: `riskLevel`, `scopes[].sensitive`,
`dataAccess[]`, `serverUrl`, per-server `icon`. Layout: header (KeyRound icon +
client name) → high-risk warning Alert → ConsentSummary (4-tile grid) →
OAuthDetails (4-tile grid) → MCPServerCards → Security Notice → Actions
(Cancel / Authorize N Servers) → footer (ToS + Privacy).

### Backend `/authorize` flow as it stands today

Two parallel endpoints serve `/authorize`:

1. **Vue Router `/authorize`** — `meta.requiresAuth: false`, loads
   `AuthorizeView`. Calls JSON `GET /api/v1/oauth2/authorize/info`. The backend
   handler (`authorize_api.go:93-176`) **always returns 200**: when no session,
   `csrf_token` is empty and `has_session: false`; the frontend renders consent
   anyway, and `POST /consent` takes the anonymous-consent branch
   (`authorize_api.go:319`).
2. **Server-rendered `GET /authorize`** — `internal/authserver/authorize.go` does
   the three-tier session resolution from `mcp-gateway-service/CLAUDE.md`:
   `mcp_session` → `gw_session` bridge → 303 to `/sso/login?purpose=oauth2`.
   The Vue route never reaches this endpoint.

`src/api/client.ts:on401()` does `window.location.href = '/sso/login?return_to=...'`
on 401, but `/info` never returns 401 today.

## Decisions

| # | Decision |
|---|---|
| 1 | Visual + UX port only. Keep real OAuth2 wiring and current `AuthorizeInfo` payload. |
| 2 | UI primitives: radix-vue + Tailwind, mirroring shadcn. |
| 3 | Drop fields the backend does not return: `riskLevel`, `scopes[].sensitive`, `dataAccess[]`, `serverUrl`, per-server icons. |
| 4 | Icon library: add `lucide-vue-next`. |
| 5 | Drop the login branch from `AuthorizeView`. Add SSO redirect when `info.has_session === false`. |

## Design

### 1. Page layout (top → bottom)

```
<div min-h-screen bg-background>
  <ConsentHeader clientName />                          ← KeyRound icon, "Authorization Request"
  <main mx-auto max-w-3xl px-4 py-8 space-y-6>
    <ConsentSummary total enabled required />           ← 3-tile grid (drop Sensitive tile)
    <OAuthDetails clientId redirectUri />               ← 2-tile grid (drop expiresIn + responseType)
    <Separator />
    <section MCP Server Access>
      <h2>Accès aux serveurs MCP</h2>
      <p>Sélectionnez les serveurs et examinez leurs permissions</p>
      <MCPServerCard v-for server in configuredServers />
    </section>
    <UnconfiguredServersBlock v-if unconfiguredServers.length />
    <Separator />
    <SecurityNotice />                                  ← 2 generic bullets
    <Actions>
      <Button variant="outline">Refuser</Button>
      <Button variant="primary">Autoriser {enabledCount} serveur(s)</Button>
    </Actions>
    <FooterLinks />                                     ← Privacy → /privacy. ToS link omitted (no route).
  </main>
</div>
```

UI labels are French to match the rest of `mcp-gateway-frontend` (per its
CLAUDE.md). The mockup's English copy is translated where used verbatim.

### 2. `ConsentHeader.vue`

- `<KeyRound>` icon from `lucide-vue-next` inside a `bg-primary` circle.
- `clientName` rendered next to a 2-letter avatar fallback (`clientName.slice(0,2).toUpperCase()`).
- Sub-text: `« demande l'autorisation d'accéder à vos serveurs MCP en votre nom. »`
- No `clientLogo` / `clientUrl` — backend does not return them.

### 3. `ConsentSummary.vue`

- Header: `<Shield>` icon + "Récapitulatif de l'autorisation".
- Description: `« Vous autorisez l'accès à {enabledServers} serveur(s) sur {totalServers}. »`,
  plus `« {requiredServers} requis pour cette application. »` when `requiredServers > 0`.
- Three tiles: `Total Serveurs`, `Activés`, `Requis`. **Sensitive tile dropped.**

### 4. `OAuthDetails.vue`

- Header: `<Info>` icon + "Détails OAuth2".
- Two `<code>` tiles: `Client ID` (with `<Key>` icon), `Redirect URI` (with `<Globe>` icon).
- `expiresIn` / `responseType` tiles dropped (no payload data; `responseType` is
  always `"code"` for this endpoint but rendering it adds no signal).

### 5. `MCPServerCard.vue`

Per-server card, replaces the existing inline `<div>` row in `AuthorizeView.vue`.

| consent-page (React) | Vue port |
|---|---|
| `name` | `server.name` |
| `icon` | placeholder `<Server>` from `lucide-vue-next` (always) |
| `description` prop | dropped — `AuthorizeServer` has no `description` field |
| `required` badge | rendered when `preConfigured === true` |
| `riskLevel` badge | dropped |
| `serverUrl` | dropped |
| `<Switch>` | preConfigured → `disabled + checked`. dynamic → bound to whole-server selection (all tools / no tools), drives `selectedTools[serverId]` via the existing `toggleServerSelection`. |
| "View scopes & permissions (N)" collapsible | "Voir les outils ({N})" — N = `server.tools.length`. Wraps the tool list. |
| Scope row | One row per `tool`. `tool.name` as `<code class="font-mono">`, `tool.description` as muted text below. Dynamic mode: leading checkbox bound to `isToolSelected`. preConfigured: leading `<Check>` icon. |
| `sensitive` marker on scope | dropped |
| Data Access section | dropped |

`enabledCount` (consumed by the Authorize button label) = `selectedServerIds.value.length`.
`requiredCount` = `preConfigured ? configuredServers.length : 0`.

### 6. `UnconfiguredServersBlock.vue`

Carries over the existing AuthorizeView block for Zoho-style servers without a
user row (`configured === false`). Restyle to match the new card aesthetic: an
amber-tinted `<div>` with one row per server, server name on the left and a
`Voir documentation →` link to `docs_url` on the right when present. No
functional change.

### 7. `script setup` changes

**Preserved verbatim** from existing `AuthorizeView.vue`:

- Route-query refs: `clientId`, `redirectUri`, `codeChallenge`, `codeChallengeMethod`, `state`.
- UI refs: `loading`, `submitting`, `errorMessage`, `fatalError`, `clientName`,
  `servers`, `configuredServers`, `unconfiguredServers`, `csrfToken`, `preConfigured`.
- Selection state: `expandedServers`, `selectedTools`, `selectedServerIds`,
  `selectedToolIds`.
- Helpers: `isServerSelected`, `isToolSelected`, `toggleServer`,
  `toggleServerSelection`, `toggleToolSelection`, `initializeSelections`.
- Handlers: `handleConsent`, `handleDeny`.

**Removed:**

- `step` ref and the `'login' | 'consent'` template branches.
- `username`, `password` refs.
- `handleLogin` function.
- The `<form @submit.prevent="handleLogin">` block.

**Added inside `fetchInfo`, immediately after the `getInfo` call returns:**

```ts
const info = await authorizeApi.getInfo(clientId.value, redirectUri.value)

if (!info.has_session) {
  const currentUrl = window.location.pathname + window.location.search
  window.location.href = '/sso/login?purpose=oauth2&return_to=' + encodeURIComponent(currentUrl)
  return
}

clientName.value = info.client_name
servers.value = info.servers
preConfigured.value = info.servers.length > 0
if (info.csrf_token) csrfToken.value = info.csrf_token
initializeSelections()
```

`AuthorizeInfo.has_session` is already declared in `src/types/oauth2.ts:54`, so
no type change is required.

The `purpose=oauth2` query parameter is **required**: the admin SSO callback
branches on it to mint an `mcp_session` cookie instead of the admin
`gw_session` (see `mcp-gateway-service/CLAUDE.md` → "OAuth2 `/authorize`
login"). Omitting it would route through the admin-only login path and break
non-admin end users.

### 8. Component file layout

```
src/components/consent/
  ConsentHeader.vue
  ConsentSummary.vue
  OAuthDetails.vue
  MCPServerCard.vue
  UnconfiguredServersBlock.vue
src/components/ui/                    # add only what does not already exist
  Switch.vue                          # radix-vue SwitchRoot / SwitchThumb
  Separator.vue                       # radix-vue SeparatorRoot
  Badge.vue                           # plain Tailwind variants (default / outline / secondary)
  # Button: reuse existing component if present in src/components/ui/IconActionButton.vue's neighbourhood;
  #        otherwise add a minimal Button.vue with variants (primary / outline)
```

Each consent component imports its own lucide icons and stays self-contained.
`MCPServerCard.vue` receives the server object plus the four toggle helpers as
props or via injection — to be decided at implementation time based on the
shape the planning step prefers.

### 9. Dependency change

```diff
  "dependencies": {
+   "lucide-vue-next": "^0.460.0"
  }
```

Tree-shakeable; only imported icons land in the bundle.

## Behavioral changes vs. today

| Concern | Before | After |
|---|---|---|
| Login UI in `AuthorizeView` | Present but unreachable | Removed |
| No-session call to `/info` | Renders consent, anonymous `/consent` succeeds | Redirects to `/sso/login?purpose=oauth2&return_to=…`; user lands back on `/authorize` with `mcp_session` cookie |
| Visual layout | Plain card on grey background, French | Mockup-style header + summary + cards + footer, French |
| Sensitive markers, risk badges, data-access blocks | n/a | n/a (not added) |
| OAuth flow endpoints | unchanged | unchanged |

The behavioral change affects only the no-session path. Sessions established
via the admin SSO bridge (mcp_session or gw_session) continue to land directly
on consent. Already-authorized clients (where `info.has_session === true`)
continue to receive a `csrf_token` and render consent unchanged.

## Open implementation choices (deferred to planning step)

- Whether `MCPServerCard` consumes the toggle helpers via props or via a
  `provide` / `inject` "consent context". Defer until the plan walks the
  call sites.
- Whether to colocate the small icon SVG primitives under `components/ui/`
  or import them directly from `lucide-vue-next` in each consumer (likely
  the latter — it is the documented usage pattern).
- Exact pin for `lucide-vue-next` to be chosen against the latest
  Vue 3.5-compatible release at install time.

## Out of scope

- No SSO-bridge changes on the backend.
- No changes to `LoginView.vue`, `OAuth2View.vue`, or
  `ServerAuthorizationsView.vue`.
- No new fields on `AuthorizeServer` or `AuthorizeInfo`.
- No e2e test scaffolding; existing `vue-tsc` build + lint are the only
  verification gates this spec commits to.
