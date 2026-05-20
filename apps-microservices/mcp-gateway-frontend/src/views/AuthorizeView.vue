<template>
  <div class="min-h-screen bg-gray-50 dark:bg-gray-950 flex flex-col">
    <ConsentHeader :client-name="clientName" />

    <!-- Loading -->
    <div v-if="loading" class="flex-1 flex items-center justify-center px-4">
      <div
        class="bg-white dark:bg-gray-900 rounded-lg shadow-theme-md p-8 text-center w-full max-w-md"
      >
        <Loader2 class="h-8 w-8 mx-auto text-brand-500 animate-spin motion-reduce:animate-none" />
        <p class="mt-3 text-base text-gray-600 dark:text-gray-400">Chargement…</p>
      </div>
    </div>

    <!-- Fatal error -->
    <div v-else-if="fatalError" class="flex-1 flex items-center justify-center px-4">
      <div
        class="bg-white dark:bg-gray-900 rounded-lg shadow-theme-md p-8 w-full max-w-md text-center"
      >
        <AlertTriangle class="h-10 w-10 mx-auto text-error-500 mb-3" />
        <h1 class="text-xl font-bold text-gray-900 dark:text-white mb-2">
          Erreur d'autorisation
        </h1>
        <p class="text-base text-error-600 dark:text-error-400 mb-6">{{ fatalError }}</p>
        <button
          type="button"
          class="inline-flex items-center justify-center py-2 px-4 bg-brand-500 text-white font-medium rounded-md hover:bg-brand-600 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500/60 focus-visible:ring-offset-2 dark:focus-visible:ring-offset-gray-900 transition-colors motion-reduce:transition-none"
          @click="retry"
        >
          Réessayer
        </button>
      </div>
    </div>

    <!-- Consent -->
    <main v-else class="mx-auto max-w-3xl w-full px-4 py-8 flex-1">
      <div class="space-y-6">
        <ConsentSummary :client-name="clientName" />

        <Separator />

        <section>
          <div class="mb-4">
            <h2 class="text-lg font-semibold text-gray-900 dark:text-white">
              Accès aux serveurs MCP
            </h2>
            <p class="text-base text-gray-600 dark:text-gray-400 mt-1">
              Sélectionnez les serveurs et examinez leurs permissions
            </p>
          </div>

          <div
            v-if="errorMessage"
            class="mb-4 p-3 bg-error-50 dark:bg-error-500/15 border border-error-200 dark:border-error-500/30 rounded-md text-sm text-error-600 dark:text-error-400"
            role="alert"
          >
            {{ errorMessage }}
          </div>

          <div
            class="rounded-lg border border-gray-200 dark:border-gray-800 divide-y divide-gray-200 dark:divide-gray-800 overflow-hidden bg-white dark:bg-gray-900"
          >
            <MCPServerCard
              v-for="server in configuredServers"
              :key="server.id"
              :server="server"
              :pre-configured="preConfigured"
              :expanded="expandedServers.has(server.id)"
              :selected-tools="selectedTools.get(server.id)"
              @toggle-tool="toggleToolSelection"
              @toggle-expand="toggleServer"
            />
          </div>
        </section>

        <UnconfiguredServersBlock
          v-if="unconfiguredServers.length > 0"
          :servers="unconfiguredServers"
        />

        <Separator />

        <div class="rounded-lg bg-gray-100 dark:bg-gray-800/50 p-4">
          <h3 class="text-sm font-semibold text-gray-900 dark:text-white mb-2">
            Informations de sécurité
          </h3>
          <ul class="space-y-1.5 text-sm text-gray-600 dark:text-gray-400">
            <li>Vous pouvez révoquer cet accès à tout moment depuis vos paramètres.</li>
            <li>Tous les appels d'API sont journalisés et auditables.</li>
          </ul>
        </div>

        <div class="flex flex-col gap-3 sm:flex-row sm:justify-end">
          <button
            type="button"
            class="sm:order-1 py-2 px-4 min-h-[44px] bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 font-medium rounded-md hover:bg-gray-300 dark:hover:bg-gray-600 focus:outline-none focus-visible:ring-2 focus-visible:ring-gray-400 focus-visible:ring-offset-2 dark:focus-visible:ring-offset-gray-950 disabled:opacity-50 disabled:cursor-not-allowed transition-colors motion-reduce:transition-none"
            :disabled="submitting"
            @click="handleDeny"
          >
            Refuser
          </button>
          <button
            type="button"
            class="sm:order-2 py-2 px-4 min-h-[44px] bg-success-600 text-white font-medium rounded-md hover:bg-success-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-success-500 focus-visible:ring-offset-2 dark:focus-visible:ring-offset-gray-950 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2 transition-colors motion-reduce:transition-none"
            :disabled="submitting || (!preConfigured && selectedServerIds.length === 0)"
            @click="handleConsent"
          >
            <Loader2 v-if="submitting" class="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden="true" />
            Autoriser {{ enabledServersCount }} serveur{{ enabledServersCount !== 1 ? 's' : '' }}
          </button>
        </div>

        <p class="text-center text-xs text-gray-600 dark:text-gray-400">
          En autorisant, vous acceptez la
          <RouterLink
            to="/privacy"
            class="underline underline-offset-2 hover:text-gray-900 dark:hover:text-white focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500/40 rounded"
          >
            politique de confidentialité
          </RouterLink>
          .
        </p>
      </div>
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { useRoute, RouterLink } from 'vue-router'
import { Loader2, AlertTriangle } from 'lucide-vue-next'
import { authorizeApi } from '@/api/authorize'
import type { AuthorizeServer } from '@/types/oauth2'
import ConsentHeader from '@/components/consent/ConsentHeader.vue'
import ConsentSummary from '@/components/consent/ConsentSummary.vue'
import MCPServerCard from '@/components/consent/MCPServerCard.vue'
import UnconfiguredServersBlock from '@/components/consent/UnconfiguredServersBlock.vue'
import Separator from '@/components/ui/Separator.vue'

const route = useRoute()

const clientId = computed(() => (route.query.client_id as string) || '')
const redirectUri = computed(() => (route.query.redirect_uri as string) || '')
const codeChallenge = computed(() => (route.query.code_challenge as string) || '')
const codeChallengeMethod = computed(
  () => (route.query.code_challenge_method as string) || '',
)
const state = computed(() => (route.query.state as string) || '')

const loading = ref(true)
const submitting = ref(false)
const errorMessage = ref('')
const fatalError = ref('')

const clientName = ref('')
const servers = ref<AuthorizeServer[]>([])
const csrfToken = ref('')
const preConfigured = ref(false)

const configuredServers = computed(() =>
  servers.value.filter((s) => s.configured !== false),
)
const unconfiguredServers = computed(() =>
  servers.value.filter((s) => s.configured === false),
)

const expandedServers = reactive(new Set<string>())
const selectedTools = reactive(new Map<string, Set<string>>())

const selectedServerIds = computed(() => {
  const ids: string[] = []
  for (const [serverId, tools] of selectedTools.entries()) {
    if (tools.size > 0) ids.push(serverId)
  }
  return ids
})

const selectedToolIds = computed(() => {
  const ids: string[] = []
  for (const [serverId, tools] of selectedTools.entries()) {
    for (const toolName of tools) ids.push(`${serverId}:${toolName}`)
  }
  return ids
})

const enabledServersCount = computed(() => selectedServerIds.value.length)

function toggleServer(serverId: string): void {
  if (expandedServers.has(serverId)) expandedServers.delete(serverId)
  else expandedServers.add(serverId)
}

function toggleToolSelection(serverId: string, toolName: string): void {
  let selected = selectedTools.get(serverId)
  if (!selected) {
    selected = new Set()
    selectedTools.set(serverId, selected)
  }
  if (selected.has(toolName)) selected.delete(toolName)
  else selected.add(toolName)
  selectedTools.set(serverId, new Set(selected))
}

function initializeSelections(): void {
  for (const server of servers.value) {
    const tools = server.tools || []
    selectedTools.set(server.id, new Set(tools.map((t) => t.name)))
  }
}

async function fetchInfo(): Promise<void> {
  loading.value = true
  fatalError.value = ''
  try {
    if (!clientId.value || !redirectUri.value) {
      fatalError.value = 'Paramètres manquants : client_id et redirect_uri sont requis.'
      return
    }

    const info = await authorizeApi.getInfo(clientId.value, redirectUri.value)

    if (!info.has_session) {
      const currentUrl = window.location.pathname + window.location.search
      window.location.href =
        '/sso/login?purpose=oauth2&return_to=' + encodeURIComponent(currentUrl)
      return
    }

    clientName.value = info.client_name
    servers.value = info.servers
    preConfigured.value = info.servers.length > 0
    if (info.csrf_token) csrfToken.value = info.csrf_token

    initializeSelections()
  } catch (e) {
    fatalError.value =
      e instanceof Error ? e.message : 'Impossible de charger les informations du client.'
  } finally {
    loading.value = false
  }
}

function retry(): void {
  fetchInfo()
}

async function handleConsent(): Promise<void> {
  errorMessage.value = ''
  submitting.value = true
  try {
    const response = await authorizeApi.consent({
      client_id: clientId.value,
      redirect_uri: redirectUri.value,
      code_challenge: codeChallenge.value,
      code_challenge_method: codeChallengeMethod.value,
      state: state.value,
      csrf_token: csrfToken.value,
      server_ids: selectedServerIds.value,
      tool_ids: selectedToolIds.value,
    })
    window.location.href = response.redirect_url
  } catch (e) {
    errorMessage.value =
      e instanceof Error ? e.message : "Erreur lors de l'autorisation."
  } finally {
    submitting.value = false
  }
}

function handleDeny(): void {
  const params = new URLSearchParams()
  params.set('error', 'access_denied')
  if (state.value) params.set('state', state.value)
  const separator = redirectUri.value.includes('?') ? '&' : '?'
  window.location.href = `${redirectUri.value}${separator}${params.toString()}`
}

onMounted(() => {
  fetchInfo()
})
</script>
