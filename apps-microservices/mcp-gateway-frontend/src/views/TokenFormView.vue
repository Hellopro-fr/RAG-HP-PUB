<template>
  <div class="p-6 max-w-3xl mx-auto">
    <!-- Page header -->
    <div class="mb-6 flex items-center gap-4">
      <button
        type="button"
        class="inline-flex items-center gap-1.5 text-sm text-gray-600 hover:text-gray-900"
        @click="router.push('/tokens')"
      >
        <i class="pi pi-arrow-left text-xs" />
        Retour
      </button>
      <h1 class="text-2xl font-bold text-gray-900">
        {{ isEdit ? 'Modifier le jeton' : 'Nouveau jeton' }}
      </h1>
    </div>

    <!-- Loading state (edit mode) -->
    <div v-if="loading" class="flex items-center justify-center py-20">
      <i class="pi pi-spinner pi-spin text-2xl text-gray-400" />
    </div>

    <!-- Post-creation display -->
    <div v-else-if="createdToken" class="space-y-6">
      <!-- Warning banner -->
      <div class="rounded-lg border border-amber-300 bg-amber-50 p-4">
        <div class="flex items-start gap-3">
          <i class="pi pi-exclamation-triangle text-amber-600 mt-0.5" />
          <p class="text-sm font-medium text-amber-800">
            Copiez ce jeton maintenant — il ne sera plus affich&eacute; !
          </p>
        </div>
      </div>

      <!-- Token value -->
      <div>
        <label class="block text-sm font-medium text-gray-700 mb-2">Jeton d'acc&egrave;s</label>
        <div class="relative">
          <pre class="bg-gray-900 text-green-400 rounded-lg p-4 pr-12 text-sm font-mono overflow-x-auto whitespace-pre-wrap break-all">{{ createdToken.token }}</pre>
          <button
            type="button"
            class="absolute top-2 right-2 p-2 text-gray-400 hover:text-white rounded-md hover:bg-gray-700"
            @click="clipboard.copy(createdToken.token || '', 'Jeton')"
          >
            <i class="pi pi-copy" />
          </button>
        </div>
      </div>

      <!-- Generated .mcp.json -->
      <div>
        <label class="block text-sm font-medium text-gray-700 mb-2">Configuration .mcp.json</label>
        <div class="relative">
          <pre class="bg-gray-900 text-blue-300 rounded-lg p-4 pr-12 text-sm font-mono overflow-x-auto whitespace-pre-wrap">{{ generatedMcpJson }}</pre>
          <button
            type="button"
            class="absolute top-2 right-2 p-2 text-gray-400 hover:text-white rounded-md hover:bg-gray-700"
            @click="clipboard.copy(generatedMcpJson, 'Configuration .mcp.json')"
          >
            <i class="pi pi-copy" />
          </button>
        </div>
      </div>

      <!-- Back button -->
      <div class="flex justify-end">
        <button
          type="button"
          class="px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-md hover:bg-blue-700"
          @click="router.push('/tokens')"
        >
          Retour aux jetons
        </button>
      </div>
    </div>

    <!-- Step form -->
    <template v-else>
      <!-- Step tabs -->
      <StepTabs
        :steps="stepLabels"
        :current-step="currentStep"
        :completed-steps="completedSteps"
        @update:current-step="goToStep"
      />

      <!-- Step content -->
      <div class="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
        <!-- Step 1: Informations de base -->
        <div v-show="currentStep === 0" class="space-y-4">
          <!-- Name -->
          <div>
            <label for="form-name" class="block text-sm font-medium text-gray-700 mb-1">
              Nom <span class="text-red-500">*</span>
            </label>
            <input
              id="form-name"
              v-model="form.name"
              type="text"
              class="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:ring-blue-500 focus:border-blue-500"
              placeholder="Mon jeton MCP"
            />
          </div>

          <!-- Description -->
          <div>
            <label for="form-description" class="block text-sm font-medium text-gray-700 mb-1">
              Description
            </label>
            <textarea
              id="form-description"
              v-model="form.description"
              rows="2"
              class="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:ring-blue-500 focus:border-blue-500"
              placeholder="Description optionnelle du jeton"
            />
          </div>

          <!-- Server name for .mcp.json -->
          <div>
            <label for="form-server-name" class="block text-sm font-medium text-gray-700 mb-1">
              Nom du serveur (.mcp.json)
            </label>
            <input
              id="form-server-name"
              v-model="form.serverName"
              type="text"
              class="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:ring-blue-500 focus:border-blue-500"
              placeholder="hellopro-gateway"
            />
            <p class="text-xs text-gray-400 mt-1">Cl&eacute; utilis&eacute;e dans le fichier .mcp.json g&eacute;n&eacute;r&eacute;</p>
          </div>

          <!-- MCP command select -->
          <div>
            <label for="form-mcp-command" class="block text-sm font-medium text-gray-700 mb-1">
              Commande MCP
            </label>
            <select
              id="form-mcp-command"
              v-model="form.mcp_command"
              class="w-full border border-gray-300 rounded-md px-3 py-2 text-sm"
            >
              <option value="npx">npx</option>
              <option value="bunx">bunx</option>
              <option value="deno">deno</option>
              <option value="uvx">uvx</option>
              <option value="docker">docker</option>
              <option value="custom">Personnalis&eacute;e</option>
            </select>
          </div>

          <!-- Custom command fields -->
          <template v-if="form.mcp_command === 'custom'">
            <div>
              <label for="form-custom-command" class="block text-sm font-medium text-gray-700 mb-1">
                Commande personnalis&eacute;e
              </label>
              <input
                id="form-custom-command"
                v-model="form.customCommand"
                type="text"
                class="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:ring-blue-500 focus:border-blue-500"
                placeholder="my-custom-command"
              />
            </div>
            <div>
              <label for="form-custom-args" class="block text-sm font-medium text-gray-700 mb-1">
                Pr&eacute;fixe d'arguments
              </label>
              <input
                id="form-custom-args"
                v-model="form.customArgsPrefix"
                type="text"
                class="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:ring-blue-500 focus:border-blue-500"
                placeholder="--flag value"
              />
              <p class="text-xs text-gray-400 mt-1">Arguments plac&eacute;s avant l'URL du gateway</p>
            </div>
          </template>
        </div>

        <!-- Step 2: Serveurs et outils -->
        <div v-show="currentStep === 1">
          <DragDropPanel :drag-drop="dragDrop" />
        </div>

        <!-- Step 3: Expiration et verification -->
        <div v-show="currentStep === 2" class="space-y-4">
          <!-- Expiration toggle -->
          <div>
            <div class="flex items-center gap-2 mb-2">
              <input
                id="form-expires"
                v-model="expiresEnabled"
                type="checkbox"
                class="rounded border-gray-300 text-blue-600"
              />
              <label for="form-expires" class="text-sm font-medium text-gray-700">
                D&eacute;finir une date d'expiration
              </label>
            </div>
            <input
              v-if="expiresEnabled"
              v-model="form.expires_at"
              type="datetime-local"
              class="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:ring-blue-500 focus:border-blue-500"
            />
          </div>

          <!-- Allow HTTP -->
          <div class="flex items-center gap-2">
            <input
              id="form-allow-http"
              v-model="form.allow_http"
              type="checkbox"
              class="rounded border-gray-300 text-blue-600"
            />
            <label for="form-allow-http" class="text-sm text-gray-700">
              Autoriser les connexions HTTP (non-HTTPS)
            </label>
          </div>

          <!-- Summary -->
          <div class="mt-6">
            <h3 class="text-sm font-semibold text-gray-900 mb-3">R&eacute;capitulatif</h3>
            <dl class="divide-y divide-gray-100">
              <div class="py-2 grid grid-cols-3 gap-4">
                <dt class="text-sm font-medium text-gray-500">Nom</dt>
                <dd class="text-sm text-gray-900 col-span-2">{{ form.name }}</dd>
              </div>
              <div v-if="form.description" class="py-2 grid grid-cols-3 gap-4">
                <dt class="text-sm font-medium text-gray-500">Description</dt>
                <dd class="text-sm text-gray-900 col-span-2">{{ form.description }}</dd>
              </div>
              <div class="py-2 grid grid-cols-3 gap-4">
                <dt class="text-sm font-medium text-gray-500">Commande</dt>
                <dd class="text-sm text-gray-900 col-span-2 font-mono">
                  {{ form.mcp_command === 'custom' ? (form.customCommand || 'custom') : form.mcp_command }}
                </dd>
              </div>
              <div class="py-2 grid grid-cols-3 gap-4">
                <dt class="text-sm font-medium text-gray-500">Serveurs</dt>
                <dd class="text-sm text-gray-900 col-span-2">
                  {{ dragDrop.selectedCount.value.servers }} serveur(s), {{ dragDrop.selectedCount.value.tools }} outil(s)
                </dd>
              </div>
              <div class="py-2 grid grid-cols-3 gap-4">
                <dt class="text-sm font-medium text-gray-500">Expiration</dt>
                <dd class="text-sm text-gray-900 col-span-2">
                  {{ expiresEnabled && form.expires_at ? form.expires_at : 'Aucune' }}
                </dd>
              </div>
              <div class="py-2 grid grid-cols-3 gap-4">
                <dt class="text-sm font-medium text-gray-500">HTTP autoris&eacute;</dt>
                <dd class="text-sm text-gray-900 col-span-2">{{ form.allow_http ? 'Oui' : 'Non' }}</dd>
              </div>
            </dl>
          </div>
        </div>
      </div>

      <!-- Navigation buttons -->
      <div class="flex justify-between mt-6">
        <button
          v-if="currentStep > 0"
          type="button"
          class="px-4 py-2 text-sm font-medium text-gray-700 bg-gray-100 rounded-md hover:bg-gray-200"
          @click="goBack"
        >
          Pr&eacute;c&eacute;dent
        </button>
        <div v-else />

        <div class="flex gap-3">
          <button
            type="button"
            class="px-4 py-2 text-sm font-medium text-gray-700 bg-gray-100 rounded-md hover:bg-gray-200"
            @click="router.push('/tokens')"
          >
            Annuler
          </button>
          <button
            v-if="currentStep < 2"
            type="button"
            class="px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-md hover:bg-blue-700 disabled:opacity-50"
            :disabled="!canGoNext"
            @click="goNext"
          >
            Suivant
          </button>
          <button
            v-if="currentStep === 2"
            type="button"
            class="px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-md hover:bg-blue-700 disabled:opacity-50"
            :disabled="submitting"
            @click="handleSubmit"
          >
            <i v-if="submitting" class="pi pi-spinner pi-spin mr-1" />
            {{ isEdit ? 'Enregistrer' : 'Cr&eacute;er' }}
          </button>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useServersStore } from '@/stores/servers'
import { useToast } from '@/composables/useToast'
import { useClipboard } from '@/composables/useClipboard'
import { useDragDrop } from '@/composables/useDragDrop'
import { tokensApi } from '@/api/tokens'
import StepTabs from '@/components/shared/StepTabs.vue'
import DragDropPanel from '@/components/shared/DragDropPanel.vue'
import type { ScopeToken, CreateTokenRequest } from '@/types/token'

const route = useRoute()
const router = useRouter()
const serversStore = useServersStore()
const toast = useToast()
const clipboard = useClipboard()
const dragDrop = useDragDrop()

const stepLabels = ['Informations de base', 'Serveurs et outils', 'Expiration et v\u00e9rification']
const currentStep = ref(0)
const loading = ref(false)
const submitting = ref(false)
const expiresEnabled = ref(false)
const createdToken = ref<ScopeToken | null>(null)

const isEdit = computed(() => !!route.params.id)

const form = reactive({
  name: '',
  description: '',
  serverName: 'hellopro-gateway',
  mcp_command: 'npx',
  customCommand: '',
  customArgsPrefix: '',
  expires_at: '',
  allow_http: true
})

const completedSteps = computed(() => {
  const completed: number[] = []
  if (isStep1Valid.value) completed.push(0)
  if (isStep1Valid.value) completed.push(1)
  return completed
})

const isStep1Valid = computed(() => {
  return !!form.name.trim()
})

const canGoNext = computed(() => {
  if (currentStep.value === 0) return isStep1Valid.value
  if (currentStep.value === 1) return true
  return false
})

const generatedMcpJson = computed(() => {
  if (!createdToken.value) return ''
  const command = form.mcp_command === 'custom'
    ? form.customCommand || 'custom-command'
    : form.mcp_command
  const serverName = form.serverName || 'hellopro-gateway'
  const tokenValue = createdToken.value.token || ''
  const gatewayUrl = window.location.origin

  const argsMap: Record<string, string[]> = {
    npx: ['-y', 'mcp-remote', gatewayUrl + '/sse'],
    bunx: ['mcp-remote', gatewayUrl + '/sse'],
    deno: ['run', '--allow-net', 'npm:mcp-remote', gatewayUrl + '/sse'],
    uvx: ['mcp-remote', gatewayUrl + '/sse'],
    docker: ['run', '-i', '--rm', 'mcp-remote', gatewayUrl + '/sse']
  }

  let args: string[]
  if (form.mcp_command === 'custom') {
    const prefixArgs = form.customArgsPrefix.trim()
      ? form.customArgsPrefix.trim().split(/\s+/)
      : []
    args = [...prefixArgs, gatewayUrl + '/sse']
  } else {
    args = argsMap[form.mcp_command] || [gatewayUrl + '/sse']
  }

  return JSON.stringify(
    { mcpServers: { [serverName]: { command, args, env: { MCP_TOKEN: tokenValue } } } },
    null,
    2
  )
})

onMounted(async () => {
  if (!serversStore.servers.length) await serversStore.fetchServers()

  if (isEdit.value) {
    loading.value = true
    try {
      const token = await tokensApi.get(route.params.id as string)
      form.name = token.name
      form.description = token.description || ''
      form.mcp_command = token.mcp_command || 'npx'
      if (token.expires_at) {
        expiresEnabled.value = true
        form.expires_at = token.expires_at.slice(0, 16)
      }

      dragDrop.initWithSelection(serversStore.servers, token.server_ids, token.server_tools)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Erreur lors du chargement du jeton')
      router.push('/tokens')
    } finally {
      loading.value = false
    }
  } else {
    dragDrop.init(serversStore.servers)
  }
})

function goToStep(step: number) {
  if (step < currentStep.value || completedSteps.value.includes(step)) {
    currentStep.value = step
  }
}

function goNext() {
  if (canGoNext.value && currentStep.value < 2) {
    currentStep.value++
  }
}

function goBack() {
  if (currentStep.value > 0) {
    currentStep.value--
  }
}

async function handleSubmit() {
  submitting.value = true
  try {
    const serverIds = dragDrop.getServerIds()
    const serverTools = dragDrop.getServerTools()

    const data: CreateTokenRequest = {
      name: form.name,
      description: form.description || undefined,
      server_ids: serverIds,
      server_tools: serverTools.length ? serverTools : undefined,
      mcp_command: form.mcp_command === 'custom'
        ? form.customCommand || 'custom'
        : form.mcp_command,
      expires_at: expiresEnabled.value && form.expires_at
        ? new Date(form.expires_at).toISOString()
        : undefined,
      allow_http: form.allow_http
    }

    if (isEdit.value) {
      await tokensApi.update(route.params.id as string, data)
      toast.success('Jeton mis \u00e0 jour')
      router.push('/tokens')
    } else {
      const result = await tokensApi.create(data)
      createdToken.value = result
    }
  } catch (err) {
    toast.error(err instanceof Error ? err.message : 'Erreur')
  } finally {
    submitting.value = false
  }
}
</script>
