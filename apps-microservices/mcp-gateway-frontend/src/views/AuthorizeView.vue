<template>
  <div class="min-h-screen flex items-center justify-center bg-gray-100">
    <div class="w-full max-w-md">
      <!-- Loading state -->
      <div v-if="loading" class="bg-white rounded-lg shadow-md p-8 text-center">
        <i class="pi pi-spinner pi-spin text-2xl text-blue-600" />
        <p class="mt-3 text-gray-600">Chargement...</p>
      </div>

      <!-- Error state (fatal, e.g. invalid client_id) -->
      <div v-else-if="fatalError" class="bg-white rounded-lg shadow-md p-8">
        <div class="text-center">
          <i class="pi pi-exclamation-triangle text-3xl text-red-500 mb-3" />
          <h1 class="text-xl font-bold text-gray-900 mb-2">Erreur d'autorisation</h1>
          <p class="text-sm text-red-600">{{ fatalError }}</p>
        </div>
      </div>

      <!-- Login step -->
      <div v-else-if="step === 'login'" class="bg-white rounded-lg shadow-md p-8">
        <h1 class="text-2xl font-bold text-center text-gray-900 mb-2">MCP Gateway</h1>
        <p class="text-sm text-center text-gray-600 mb-6">
          Connexion pour <strong>{{ clientName }}</strong>
        </p>

        <div
          v-if="errorMessage"
          class="mb-4 p-3 bg-red-50 border border-red-200 rounded-md text-sm text-red-700"
        >
          {{ errorMessage }}
        </div>

        <form @submit.prevent="handleLogin">
          <div class="mb-4">
            <label for="username" class="block text-sm font-medium text-gray-700 mb-1">
              Nom d'utilisateur
            </label>
            <input
              id="username"
              v-model="username"
              type="text"
              required
              class="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            />
          </div>

          <div class="mb-6">
            <label for="password" class="block text-sm font-medium text-gray-700 mb-1">
              Mot de passe
            </label>
            <input
              id="password"
              v-model="password"
              type="password"
              required
              class="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            />
          </div>

          <button
            type="submit"
            :disabled="submitting"
            class="w-full py-2 px-4 bg-blue-600 text-white font-medium rounded-md hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
          >
            <i v-if="submitting" class="pi pi-spinner pi-spin" />
            Se connecter
          </button>
        </form>
      </div>

      <!-- Consent step -->
      <div v-else-if="step === 'consent'" class="bg-white rounded-lg shadow-md p-8">
        <h1 class="text-xl font-bold text-center text-gray-900 mb-1">Autorisation</h1>
        <p class="text-sm text-center text-gray-600 mb-6">
          <strong>{{ clientName }}</strong> demande l'acc&egrave;s aux outils suivants
        </p>

        <div
          v-if="errorMessage"
          class="mb-4 p-3 bg-red-50 border border-red-200 rounded-md text-sm text-red-700"
        >
          {{ errorMessage }}
        </div>

        <!-- Server list -->
        <div class="space-y-2 mb-6 max-h-80 overflow-y-auto">
          <div
            v-for="server in servers"
            :key="server.id"
            class="border border-gray-200 rounded-md"
          >
            <!-- Server header -->
            <div
              class="flex items-center gap-2 px-3 py-2 cursor-pointer hover:bg-gray-50"
              @click="toggleServer(server.id)"
            >
              <i
                class="pi pi-chevron-right text-xs text-gray-400 transition-transform duration-200"
                :class="{ 'rotate-90': expandedServers.has(server.id) }"
              />
              <!-- Pre-configured: read-only checkmark -->
              <i
                v-if="preConfigured"
                class="pi pi-check-circle text-green-500"
              />
              <!-- Dynamic: interactive checkbox -->
              <input
                v-else
                type="checkbox"
                :checked="isServerSelected(server.id)"
                class="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                @click.stop="toggleServerSelection(server.id)"
              />
              <span class="text-sm font-medium text-gray-800 flex-1">{{ server.name }}</span>
              <span class="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded-full">
                {{ server.tools.length }} outil{{ server.tools.length > 1 ? 's' : '' }}
              </span>
            </div>

            <!-- Tools list (collapsible) -->
            <div
              v-if="expandedServers.has(server.id)"
              class="border-t border-gray-100 px-3 py-2 space-y-1"
            >
              <div
                v-for="tool in server.tools"
                :key="`${server.id}:${tool.name}`"
                class="flex items-center gap-2 py-1"
              >
                <i
                  v-if="preConfigured"
                  class="pi pi-check text-green-400 text-xs ml-4"
                />
                <input
                  v-else
                  type="checkbox"
                  :checked="isToolSelected(server.id, tool.name)"
                  class="ml-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                  @change="toggleToolSelection(server.id, tool.name)"
                />
                <div class="flex-1 min-w-0">
                  <span class="text-sm text-gray-700">{{ tool.name }}</span>
                  <p
                    v-if="tool.description"
                    class="text-xs text-gray-400 truncate"
                    :title="tool.description"
                  >
                    {{ tool.description }}
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Action buttons -->
        <div class="flex gap-3">
          <button
            type="button"
            class="flex-1 py-2 px-4 bg-gray-200 text-gray-700 font-medium rounded-md hover:bg-gray-300"
            :disabled="submitting"
            @click="handleDeny"
          >
            Refuser
          </button>
          <button
            type="button"
            class="flex-1 py-2 px-4 bg-green-600 text-white font-medium rounded-md hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
            :disabled="submitting || (!preConfigured && selectedServerIds.length === 0)"
            @click="handleConsent"
          >
            <i v-if="submitting" class="pi pi-spinner pi-spin" />
            Autoriser
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { authorizeApi } from '@/api/authorize'
import type { AuthorizeServer } from '@/types/oauth2'

const route = useRoute()

// OAuth2 query params
const clientId = computed(() => (route.query.client_id as string) || '')
const redirectUri = computed(() => (route.query.redirect_uri as string) || '')
const codeChallenge = computed(() => (route.query.code_challenge as string) || '')
const codeChallengeMethod = computed(() => (route.query.code_challenge_method as string) || '')
const state = computed(() => (route.query.state as string) || '')

// UI state
const step = ref<'login' | 'consent'>('login')
const loading = ref(true)
const submitting = ref(false)
const errorMessage = ref('')
const fatalError = ref('')

// Data
const clientName = ref('')
const servers = ref<AuthorizeServer[]>([])
const csrfToken = ref('')
const preConfigured = ref(false)

// Login form
const username = ref('')
const password = ref('')

// Consent state
const expandedServers = reactive(new Set<string>())
const selectedTools = reactive(new Map<string, Set<string>>())

// Computed: list of selected server IDs (servers with at least one tool selected)
const selectedServerIds = computed(() => {
  const ids: string[] = []
  for (const [serverId, tools] of selectedTools.entries()) {
    if (tools.size > 0) {
      ids.push(serverId)
    }
  }
  return ids
})

// Computed: list of selected tool IDs in "server_id:tool_name" format
const selectedToolIds = computed(() => {
  const ids: string[] = []
  for (const [serverId, tools] of selectedTools.entries()) {
    for (const toolName of tools) {
      ids.push(`${serverId}:${toolName}`)
    }
  }
  return ids
})

function isServerSelected(serverId: string): boolean {
  const server = servers.value.find((s) => s.id === serverId)
  if (!server) return false
  const selected = selectedTools.get(serverId)
  if (!selected) return false
  return selected.size === server.tools.length
}

function isToolSelected(serverId: string, toolName: string): boolean {
  const selected = selectedTools.get(serverId)
  return selected ? selected.has(toolName) : false
}

function toggleServer(serverId: string): void {
  if (expandedServers.has(serverId)) {
    expandedServers.delete(serverId)
  } else {
    expandedServers.add(serverId)
  }
}

function toggleServerSelection(serverId: string): void {
  const server = servers.value.find((s) => s.id === serverId)
  if (!server) return

  if (isServerSelected(serverId)) {
    // Deselect all tools
    selectedTools.set(serverId, new Set())
  } else {
    // Select all tools
    selectedTools.set(serverId, new Set(server.tools.map((t) => t.name)))
  }
}

function toggleToolSelection(serverId: string, toolName: string): void {
  let selected = selectedTools.get(serverId)
  if (!selected) {
    selected = new Set()
    selectedTools.set(serverId, selected)
  }

  if (selected.has(toolName)) {
    selected.delete(toolName)
  } else {
    selected.add(toolName)
  }
  // Trigger reactivity
  selectedTools.set(serverId, new Set(selected))
}

function initializeSelections(): void {
  for (const server of servers.value) {
    if (preConfigured.value) {
      // Pre-configured: all selected by default (read-only)
      selectedTools.set(server.id, new Set(server.tools.map((t) => t.name)))
    } else {
      // Dynamic: all selected by default, user can deselect
      selectedTools.set(server.id, new Set(server.tools.map((t) => t.name)))
    }
  }
}

async function fetchInfo(): Promise<void> {
  loading.value = true
  try {
    if (!clientId.value || !redirectUri.value) {
      fatalError.value = 'Paramètres manquants : client_id et redirect_uri sont requis.'
      return
    }

    const info = await authorizeApi.getInfo(clientId.value, redirectUri.value)
    clientName.value = info.client_name
    servers.value = info.servers

    // Determine if pre-configured (servers come from client config, not user choice)
    // If the client has servers assigned, it's pre-configured
    preConfigured.value = info.servers.length > 0

    if (info.has_session && info.has_consent) {
      // Already authorized — skip to consent auto-approve or redirect
      // The backend should handle this, but we show consent step as fallback
      step.value = 'consent'
      initializeSelections()
    } else if (info.has_session) {
      // Session exists, skip login
      step.value = 'consent'
      initializeSelections()
    } else {
      step.value = 'login'
    }
  } catch (e) {
    fatalError.value = e instanceof Error ? e.message : 'Impossible de charger les informations du client.'
  } finally {
    loading.value = false
  }
}

async function handleLogin(): Promise<void> {
  errorMessage.value = ''
  submitting.value = true
  try {
    const response = await authorizeApi.login({
      username: username.value,
      password: password.value,
      client_id: clientId.value,
      redirect_uri: redirectUri.value,
      code_challenge: codeChallenge.value,
      code_challenge_method: codeChallengeMethod.value,
      state: state.value
    })

    if (!response.success) {
      errorMessage.value = response.error || 'Identifiants invalides.'
      return
    }

    // Store CSRF token and server info from login response
    csrfToken.value = response.csrf_token
    clientName.value = response.client_name
    servers.value = response.servers

    // If login response has servers, it's pre-configured
    preConfigured.value = response.servers.length > 0

    initializeSelections()
    step.value = 'consent'
    errorMessage.value = ''
  } catch (e) {
    errorMessage.value = e instanceof Error ? e.message : 'Erreur de connexion.'
  } finally {
    submitting.value = false
  }
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
      tool_ids: selectedToolIds.value
    })

    // Redirect to the authorization callback URL
    window.location.href = response.redirect_url
  } catch (e) {
    errorMessage.value = e instanceof Error ? e.message : 'Erreur lors de l\'autorisation.'
  } finally {
    submitting.value = false
  }
}

function handleDeny(): void {
  const params = new URLSearchParams()
  params.set('error', 'access_denied')
  if (state.value) {
    params.set('state', state.value)
  }

  const separator = redirectUri.value.includes('?') ? '&' : '?'
  window.location.href = `${redirectUri.value}${separator}${params.toString()}`
}

onMounted(() => {
  fetchInfo()
})
</script>
