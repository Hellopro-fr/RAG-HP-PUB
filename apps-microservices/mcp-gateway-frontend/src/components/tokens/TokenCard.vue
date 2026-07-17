<template>
  <div class="bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-800 shadow-theme-xs hover:shadow-theme-md transition-shadow">
    <div class="p-5">
      <!-- Row 1: Info -->
      <div class="flex flex-col sm:flex-row sm:items-start gap-4">
        <!-- Left: icon + name + status + prefix -->
        <div class="flex items-start gap-3 shrink-0">
          <div class="w-10 h-10 rounded-full bg-amber-100 dark:bg-amber-500/15 text-amber-600 dark:text-amber-400 flex items-center justify-center shrink-0">
            <i class="pi pi-lock text-lg" />
          </div>
          <div class="min-w-0">
            <div class="flex items-center gap-2 mb-1">
              <h3 class="text-sm font-semibold text-gray-900 dark:text-white truncate max-w-[200px]">
                {{ token.name }}
              </h3>
              <span
                class="text-xs px-2 py-0.5 rounded-full font-medium shrink-0"
                :class="token.is_active
                  ? 'bg-success-50 text-success-600 dark:bg-success-500/15 dark:text-success-400'
                  : 'bg-error-50 text-error-600 dark:bg-error-500/15 dark:text-error-400'"
              >
                {{ token.is_active ? 'Actif' : 'Révoqué' }}
              </span>
            </div>
            <div class="flex items-center gap-1.5">
              <code class="text-xs text-gray-600 dark:text-gray-400 bg-gray-100 dark:bg-white/5 px-2 py-1 rounded font-mono">
                {{ maskedPrefix }}
              </code>
              <button
                v-if="token.token"
                class="p-0.5 rounded hover:bg-gray-100 dark:hover:bg-white/5 text-brand-500"
                title="Copier le jeton"
                @click.stop="clipboard.copy(token.token!, 'Jeton')"
              >
                <i class="pi pi-copy text-[10px]" />
              </button>
            </div>
          </div>
        </div>

        <!-- Right: server badges, command, expiration, created_by + actions -->
        <div class="flex-1 min-w-0">
          <div class="flex flex-wrap items-center gap-2 mb-2">
            <span
              v-for="name in serverNames"
              :key="name"
              class="text-xs bg-brand-50 dark:bg-brand-500/10 text-brand-600 dark:text-brand-400 px-2 py-0.5 rounded font-mono"
            >
              {{ name }}
            </span>
            <span class="text-xs px-2 py-0.5 rounded bg-purple-100 dark:bg-purple-500/15 text-purple-700 dark:text-purple-400 font-mono">
              {{ token.mcp_command || 'npx' }}
            </span>
            <span
              v-if="leexiBadge"
              class="text-xs px-2 py-0.5 rounded bg-amber-100 dark:bg-amber-500/15 text-amber-700 dark:text-amber-400"
              :title="`Filtre Leexi : ${leexiBadge}`"
            >
              <i class="pi pi-filter text-[10px] mr-1" />Leexi: {{ leexiBadge }}
            </span>
          </div>
          <div class="flex flex-wrap items-center gap-4 text-xs text-gray-500 dark:text-gray-400">
            <div class="flex items-center gap-1.5">
              <i class="pi pi-calendar text-[10px]" />
              <span v-if="token.expires_at">Expire le {{ formatDate(token.expires_at) }}</span>
              <span v-else class="px-2 py-0.5 rounded-full font-medium bg-success-50 text-success-600 dark:bg-success-500/15 dark:text-success-400">Permanent</span>
            </div>
            <div v-if="token.created_by" class="flex items-center gap-1.5">
              <i class="pi pi-user text-[10px]" />
              <span>{{ token.created_by }}</span>
            </div>
          </div>
        </div>

        <!-- Action buttons -->
        <div class="flex items-center gap-1 shrink-0">
          <button class="p-1.5 rounded hover:bg-gray-100 dark:hover:bg-white/5 text-brand-500" title="Copier .mcp.json" @click="copyMcpJson">
            <i class="pi pi-file-export text-sm" />
          </button>
          <button v-if="token.is_active" class="p-1.5 rounded hover:bg-gray-100 dark:hover:bg-white/5 text-gray-500 dark:text-gray-400" title="Modifier" @click="emit('edit', token)">
            <i class="pi pi-pencil text-sm" />
          </button>
          <button v-if="token.is_active" class="p-1.5 rounded hover:bg-gray-100 dark:hover:bg-white/5 text-orange-500 dark:text-orange-400" title="Révoquer" @click="emit('revoke', token.id)">
            <i class="pi pi-times text-sm" />
          </button>
          <button class="p-1.5 rounded hover:bg-gray-100 dark:hover:bg-white/5 text-red-500 dark:text-error-400" title="Supprimer" @click="emit('delete', token.id)">
            <i class="pi pi-trash text-sm" />
          </button>
        </div>
      </div>

      <!-- Row 2: .mcp.json code block (full width) -->
      <div class="mt-4 pt-4 border-t border-gray-100 dark:border-gray-800">
        <div class="flex items-center justify-between mb-2 gap-2 flex-wrap">
          <div class="flex items-center gap-2">
            <span class="text-xs font-medium text-gray-600 dark:text-gray-400">.mcp.json</span>
            <div class="inline-flex rounded-md overflow-hidden border border-gray-200 dark:border-gray-700 text-[11px]">
              <button
                type="button"
                class="px-2 py-0.5 font-medium transition-colors"
                :class="authVariant === 'bearer'
                  ? 'bg-brand-500 text-white'
                  : 'bg-white dark:bg-gray-900 text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-800'"
                @click="authVariant = 'bearer'"
              >
                Bearer
              </button>
              <button
                type="button"
                class="px-2 py-0.5 font-medium transition-colors border-l border-gray-200 dark:border-gray-700"
                :class="authVariant === 'scope'
                  ? 'bg-brand-500 text-white'
                  : 'bg-white dark:bg-gray-900 text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-800'"
                @click="authVariant = 'scope'"
              >
                X-MCP-Scope-Token
              </button>
            </div>
          </div>
          <div class="flex items-center gap-3">
            <a
              href="/install-guide"
              target="_blank"
              rel="noopener noreferrer"
              class="text-xs text-brand-500 hover:text-brand-600 flex items-center gap-1"
              title="Ouvrir le guide d'installation dans un nouvel onglet"
            >
              <i class="pi pi-external-link text-[10px]" />
              Documentation
            </a>
            <button class="text-xs text-brand-500 hover:text-brand-600 flex items-center gap-1" @click="copyMcpJson">
              <i class="pi pi-copy text-[10px]" />
              Copier
            </button>
          </div>
        </div>
        <pre class="text-[11px] bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg p-3 font-mono overflow-x-auto max-h-[160px] overflow-y-auto whitespace-pre text-gray-800 dark:text-gray-300">{{ mcpJsonDisplay }}</pre>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import type { ScopeToken } from '@/types/token'
import type { InstallExecutor } from '@/types/install-guide'
import { useClipboard } from '@/composables/useClipboard'
import { useServersStore } from '@/stores/servers'

type AuthVariant = 'bearer' | 'scope'

const props = withDefaults(
  defineProps<{ token: ScopeToken; executors?: InstallExecutor[] }>(),
  { executors: () => [] }
)

const emit = defineEmits<{
  edit: [token: ScopeToken]
  revoke: [id: string]
  delete: [id: string]
}>()

const clipboard = useClipboard()
const serversStore = useServersStore()

// Auth header variant: Bearer (Claude.ai / Cursor / standard MCP clients,
// default) or X-MCP-Scope-Token (legacy, custom-header integrations). The
// gateway accepts both for /tokens-issued scope tokens.
const authVariant = ref<AuthVariant>('bearer')

// Swap the auth header line of an already-built .mcp.json string. The
// gateway routes a `mcp_*` value identically through both headers, so the
// substitution preserves behaviour and only changes wire shape.
function applyAuthHeader(json: string, variant: AuthVariant): string {
  if (variant === 'scope') return json
  return json.replace(/"X-MCP-Scope-Token:\s*/g, '"Authorization: Bearer ')
}

const maskedPrefix = computed(() => {
  const prefix = props.token.token_prefix || ''
  if (prefix.length > 8) {
    return prefix.substring(0, 8) + '...' + '\u2022'.repeat(9)
  }
  return prefix + '...' + '\u2022'.repeat(9)
})

const serverNames = computed(() => {
  return props.token.server_ids
    .map(id => {
      const server = serversStore.servers.find(s => s.id === id)
      return server?.name ?? id
    })
})

// Compact one-line summary of the Leexi ownership filter for the badge.
const leexiBadge = computed<string | null>(() => {
  const f = props.token.leexi_filter
  if (!f || f.mode === 'none') return null
  switch (f.mode) {
    case 'users':
      return `${(f.user_uuids || []).length} user(s)`
    case 'teams':
      return `${(f.team_uuids || []).length} team(s)`
    case 'creator':
      return 'creator only'
    case 'self':
      return 'connected user (self)'
    default:
      return null
  }
})

// Build the .mcp.json string. Prefer the template stored on the selected
// Package Executor (top-level mcp_config field → falls back to the
// page-builder `mcp-config` element for legacy data). When no template is
// available, fall back to a synthetic builder for built-in commands.
function buildMcpJsonString(tokenValue: string): string {
  const command = props.token.mcp_command || 'npx'
  const serverName = props.token.server_name || 'hellopro-gateway'
  const origin = window.location.origin
  const host = origin.replace(/^https?:\/\//, '')

  // 1. Try the executor's persisted template
  const exec = props.executors.find(e => e.slug === command)
  const mcpEl = Array.isArray(exec?.content)
    ? exec!.content.find((el) => el?.type === 'mcp-config')
    : null
  const template = (exec?.mcp_config as string) || mcpEl?.props?.code || ''

  if (template) {
    const allowHttp = !!props.token.allow_http
    const withAllowHttp = allowHttp
      ? template.replace(/"<allow-http>"/g, '"--allow-http"')
      : template.replace(/^[ \t]*"<allow-http>"[ \t]*,?[ \t]*\r?\n/gm, '')
    return withAllowHttp
      .replace(/https?:\/\/<gateway-url>/g, origin)
      .replace(/<gateway-url>/g, host)
      .replace(/<server-name>/g, serverName)
      .replace(/<token>/g, tokenValue)
      .replace(/<votre-token>/g, tokenValue)
  }

  // 2. Synthetic fallback for custom commands / missing executor
  const headerArg = 'X-MCP-Scope-Token: ${MCP_SCOPE_TOKEN}'
  const env = { MCP_SCOPE_TOKEN: tokenValue }
  const defaultArgs = [origin + '/mcp', '--header', headerArg]

  return JSON.stringify(
    {
      mcpServers: {
        [serverName]: {
          command,
          args: defaultArgs,
          env,
        },
      },
    },
    null,
    2
  )
}

const maskedToken = computed(() => {
  return props.token.token_prefix
    ? props.token.token_prefix.substring(0, 8) + '...' + '\u2022'.repeat(9)
    : '***'
})

// Display version uses masked token
const mcpJsonDisplay = computed(() =>
  applyAuthHeader(buildMcpJsonString(maskedToken.value), authVariant.value)
)

// Copy version uses full token if available, otherwise masked
function copyMcpJson() {
  const tokenValue = props.token.token || maskedToken.value
  clipboard.copy(
    applyAuthHeader(buildMcpJsonString(tokenValue), authVariant.value),
    'Configuration .mcp.json'
  )
}

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString('fr-FR', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit'
  })
}
</script>
