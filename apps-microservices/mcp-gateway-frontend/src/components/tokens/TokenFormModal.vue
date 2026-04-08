<template>
  <div class="fixed inset-0 bg-black/50 z-40 flex items-center justify-center" @click.self="handleClose">
    <div class="bg-white rounded-lg shadow-xl p-6 max-w-2xl w-full max-h-[90vh] overflow-y-auto">
      <!-- Post-creation result -->
      <template v-if="createdToken">
        <h2 class="text-lg font-semibold text-gray-900 mb-4">Jeton créé avec succès</h2>

        <!-- Warning -->
        <div class="flex items-start gap-3 p-4 mb-4 bg-amber-50 border border-amber-200 rounded-lg">
          <i class="pi pi-exclamation-triangle text-amber-600 mt-0.5" />
          <p class="text-sm text-amber-800">
            Copiez ce jeton maintenant — il ne sera plus affiché !
          </p>
        </div>

        <!-- Token value -->
        <div class="mb-4">
          <label class="block text-sm font-medium text-gray-700 mb-1">Jeton d'accès</label>
          <div class="flex items-center gap-2">
            <code class="flex-1 text-sm bg-gray-50 border border-gray-200 rounded-md p-3 font-mono break-all select-all">
              {{ createdToken.token }}
            </code>
            <button
              class="shrink-0 p-2 rounded hover:bg-gray-100 text-blue-600"
              title="Copier le jeton"
              @click="clipboard.copy(createdToken!.token || '', 'Jeton')"
            >
              <i class="pi pi-copy" />
            </button>
          </div>
        </div>

        <!-- .mcp.json config -->
        <div class="mb-4">
          <label class="block text-sm font-medium text-gray-700 mb-1">Configuration .mcp.json</label>
          <div class="relative">
            <pre
              class="text-sm bg-gray-50 border border-gray-200 rounded-md p-3 font-mono overflow-x-auto max-h-[200px] overflow-y-auto whitespace-pre"
            >{{ generatedMcpJson }}</pre>
            <button
              class="absolute top-2 right-2 p-1.5 rounded bg-white border border-gray-200 hover:bg-gray-50 text-blue-600"
              title="Copier la configuration"
              @click="clipboard.copy(generatedMcpJson, 'Configuration .mcp.json')"
            >
              <i class="pi pi-copy text-sm" />
            </button>
          </div>
        </div>

        <div class="flex justify-end pt-4 border-t border-gray-100">
          <button
            class="px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-md hover:bg-blue-700"
            @click="emit('close')"
          >
            Fermer
          </button>
        </div>
      </template>

      <!-- Create/Edit form -->
      <template v-else>
        <h2 class="text-lg font-semibold text-gray-900 mb-4">
          {{ token ? 'Modifier le jeton' : 'Créer un jeton d\'accès' }}
        </h2>

        <form @submit.prevent="handleSubmit" class="space-y-4">
          <!-- Token name -->
          <div>
            <label for="token-name" class="block text-sm font-medium text-gray-700 mb-1">
              Nom du jeton <span class="text-red-500">*</span>
            </label>
            <input
              id="token-name"
              v-model="form.name"
              type="text"
              required
              class="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:ring-blue-500 focus:border-blue-500"
              placeholder="dev-rag-only"
            />
          </div>

          <!-- Description -->
          <div>
            <label for="token-desc" class="block text-sm font-medium text-gray-700 mb-1">
              Description
            </label>
            <input
              id="token-desc"
              v-model="form.description"
              type="text"
              class="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:ring-blue-500 focus:border-blue-500"
              placeholder="Jeton pour l'accès développement"
            />
          </div>

          <!-- Server name in .mcp.json -->
          <div>
            <label for="token-server-name" class="block text-sm font-medium text-gray-700 mb-1">
              Nom du serveur dans .mcp.json
            </label>
            <input
              id="token-server-name"
              v-model="form.serverName"
              type="text"
              class="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:ring-blue-500 focus:border-blue-500"
              placeholder="hellopro-gateway"
            />
          </div>

          <!-- MCP command -->
          <div>
            <label for="token-mcp-command" class="block text-sm font-medium text-gray-700 mb-1">
              Commande MCP
            </label>
            <select
              id="token-mcp-command"
              v-model="form.mcp_command"
              class="w-full border border-gray-300 rounded-md px-3 py-2 text-sm"
            >
              <option value="npx">npx</option>
              <option value="bunx">bunx</option>
              <option value="deno">deno</option>
              <option value="uvx">uvx</option>
              <option value="docker">docker</option>
              <option value="custom">Personnalisé</option>
            </select>
          </div>

          <!-- Custom command fields -->
          <template v-if="form.mcp_command === 'custom'">
            <div>
              <label for="token-custom-command" class="block text-sm font-medium text-gray-700 mb-1">
                Chemin de la commande
              </label>
              <input
                id="token-custom-command"
                v-model="form.customCommand"
                type="text"
                class="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:ring-blue-500 focus:border-blue-500"
                placeholder="/usr/local/bin/mcp-client"
              />
            </div>
            <div>
              <label for="token-custom-args-prefix" class="block text-sm font-medium text-gray-700 mb-1">
                Arguments avant l'URL
              </label>
              <input
                id="token-custom-args-prefix"
                v-model="form.customArgsPrefix"
                type="text"
                class="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:ring-blue-500 focus:border-blue-500"
                placeholder="--mode remote"
              />
            </div>
            <p class="text-xs text-gray-500">
              <a href="/install-guide.html" target="_blank" class="text-blue-600 hover:underline">
                Guide d'installation des clients MCP personnalisés
              </a>
            </p>
          </template>

          <!-- Drag-and-drop panel -->
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-2">
              Serveurs et outils autorisés
            </label>
            <DragDropPanel :drag-drop="dragDrop" />
          </div>

          <!-- Expiration -->
          <div>
            <div class="flex items-center gap-2 mb-2">
              <input
                id="token-expires-toggle"
                v-model="expiresEnabled"
                type="checkbox"
                class="rounded border-gray-300 text-blue-600"
              />
              <label for="token-expires-toggle" class="text-sm text-gray-700">
                Définir une date d'expiration
              </label>
            </div>
            <input
              v-if="expiresEnabled"
              id="token-expires"
              v-model="form.expires_at"
              type="datetime-local"
              class="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:ring-blue-500 focus:border-blue-500"
            />
          </div>

          <!-- Allow HTTP -->
          <div class="flex items-center gap-2">
            <input
              id="token-allow-http"
              v-model="form.allow_http"
              type="checkbox"
              class="rounded border-gray-300 text-blue-600"
            />
            <label for="token-allow-http" class="text-sm text-gray-700">
              Autoriser les connexions HTTP (non-SSL)
            </label>
          </div>

          <!-- Actions -->
          <div class="flex justify-end gap-3 pt-4 border-t border-gray-100">
            <button
              type="button"
              class="px-4 py-2 text-sm font-medium text-gray-700 bg-gray-100 rounded-md hover:bg-gray-200"
              @click="emit('close')"
            >
              Annuler
            </button>
            <button
              type="submit"
              class="px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-md hover:bg-blue-700 disabled:opacity-50"
              :disabled="submitting"
            >
              <i v-if="submitting" class="pi pi-spinner pi-spin mr-1" />
              {{ token ? 'Enregistrer les modifications' : 'Générer le jeton' }}
            </button>
          </div>
        </form>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, computed } from 'vue'
import { tokensApi } from '@/api/tokens'
import { useServersStore } from '@/stores/servers'
import { useToast } from '@/composables/useToast'
import { useClipboard } from '@/composables/useClipboard'
import { useDragDrop } from '@/composables/useDragDrop'
import DragDropPanel from '@/components/shared/DragDropPanel.vue'
import type { ScopeToken, CreateTokenRequest } from '@/types/token'

const props = defineProps<{ token?: ScopeToken }>()
const emit = defineEmits<{ close: []; saved: [] }>()

const serversStore = useServersStore()
const toast = useToast()
const clipboard = useClipboard()
const dragDrop = useDragDrop()

const submitting = ref(false)
const expiresEnabled = ref(!!props.token?.expires_at)
const createdToken = ref<ScopeToken | null>(null)

const form = reactive({
  name: props.token?.name ?? '',
  description: props.token?.description ?? '',
  serverName: 'hellopro-gateway',
  mcp_command: props.token?.mcp_command ?? 'npx',
  customCommand: '',
  customArgsPrefix: '',
  expires_at: props.token?.expires_at ?? '',
  allow_http: true
})

onMounted(async () => {
  if (!serversStore.servers.length) {
    await serversStore.fetchServers()
  }
  if (props.token) {
    dragDrop.initWithSelection(
      serversStore.servers,
      props.token.server_ids,
      props.token.server_tools
    )
  } else {
    dragDrop.init(serversStore.servers)
  }
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

  const config = {
    mcpServers: {
      [serverName]: {
        command,
        args,
        env: { MCP_TOKEN: tokenValue }
      }
    }
  }

  return JSON.stringify(config, null, 2)
})

function handleClose() {
  if (!createdToken.value) {
    emit('close')
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

    if (props.token) {
      await tokensApi.update(props.token.id, data)
      toast.success('Jeton mis à jour')
      emit('saved')
    } else {
      const result = await tokensApi.create(data)
      createdToken.value = result
    }
  } catch (err) {
    toast.error(err instanceof Error ? err.message : 'Erreur lors de la création du jeton')
  } finally {
    submitting.value = false
  }
}
</script>
