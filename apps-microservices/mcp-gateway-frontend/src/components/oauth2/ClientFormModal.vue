<template>
  <div class="fixed inset-0 bg-black/50 z-40 flex items-center justify-center" @click.self="handleClose">
    <div class="bg-white rounded-lg shadow-xl p-6 max-w-2xl w-full max-h-[90vh] overflow-y-auto">
      <!-- Post-creation result -->
      <template v-if="createdClient">
        <h2 class="text-lg font-semibold text-gray-900 mb-4">Client OAuth2 créé avec succès</h2>

        <!-- Warning -->
        <div class="flex items-start gap-3 p-4 mb-4 bg-amber-50 border border-amber-200 rounded-lg">
          <i class="pi pi-exclamation-triangle text-amber-600 mt-0.5" />
          <p class="text-sm text-amber-800">
            Copiez ces identifiants maintenant — le secret ne sera plus affiché !
          </p>
        </div>

        <!-- Client ID -->
        <div class="mb-4">
          <label class="block text-sm font-medium text-gray-700 mb-1">Client ID</label>
          <div class="flex items-center gap-2">
            <code class="flex-1 text-sm bg-gray-50 border border-gray-200 rounded-md p-3 font-mono break-all select-all">
              {{ createdClient.id }}
            </code>
            <button
              class="shrink-0 p-2 rounded hover:bg-gray-100 text-blue-600"
              title="Copier le Client ID"
              @click="clipboard.copy(createdClient!.id, 'Client ID')"
            >
              <i class="pi pi-copy" />
            </button>
          </div>
        </div>

        <!-- Client Secret -->
        <div class="mb-4">
          <label class="block text-sm font-medium text-gray-700 mb-1">Client Secret</label>
          <div class="flex items-center gap-2">
            <code class="flex-1 text-sm bg-gray-50 border border-gray-200 rounded-md p-3 font-mono break-all select-all">
              {{ createdClient.client_secret || 'Non disponible' }}
            </code>
            <button
              v-if="createdClient.client_secret"
              class="shrink-0 p-2 rounded hover:bg-gray-100 text-blue-600"
              title="Copier le Client Secret"
              @click="clipboard.copy(createdClient!.client_secret || '', 'Client Secret')"
            >
              <i class="pi pi-copy" />
            </button>
          </div>
        </div>

        <!-- Config box -->
        <div class="p-4 mb-4 bg-blue-50 border border-blue-200 rounded-lg">
          <h3 class="text-sm font-semibold text-blue-800 mb-2">Configuration Claude.ai</h3>
          <div class="space-y-2 text-sm">
            <div class="flex items-center gap-2">
              <span class="text-blue-600 font-medium">Gateway URL :</span>
              <code class="bg-white px-2 py-0.5 rounded text-blue-900 font-mono text-xs">
                {{ gatewayMcpUrl }}
              </code>
              <button
                class="p-1 rounded hover:bg-blue-100 text-blue-600"
                @click="clipboard.copy(gatewayMcpUrl, 'Gateway URL')"
              >
                <i class="pi pi-copy text-xs" />
              </button>
            </div>
            <div class="flex items-center gap-2">
              <span class="text-blue-600 font-medium">Token endpoint :</span>
              <code class="bg-white px-2 py-0.5 rounded text-blue-900 font-mono text-xs">
                {{ tokenEndpointUrl }}
              </code>
              <button
                class="p-1 rounded hover:bg-blue-100 text-blue-600"
                @click="clipboard.copy(tokenEndpointUrl, 'Token endpoint')"
              >
                <i class="pi pi-copy text-xs" />
              </button>
            </div>
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
          {{ client ? 'Modifier le scope du client' : 'Créer un client OAuth2' }}
        </h2>

        <form @submit.prevent="handleSubmit" class="space-y-4">
          <!-- Name -->
          <div>
            <label for="oauth2-name" class="block text-sm font-medium text-gray-700 mb-1">
              Nom <span class="text-red-500">*</span>
            </label>
            <input
              id="oauth2-name"
              v-model="form.name"
              type="text"
              required
              class="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:ring-blue-500 focus:border-blue-500"
              placeholder="claude-ai-prod"
            />
          </div>

          <!-- Description -->
          <div>
            <label for="oauth2-desc" class="block text-sm font-medium text-gray-700 mb-1">
              Description
            </label>
            <input
              id="oauth2-desc"
              v-model="form.description"
              type="text"
              class="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:ring-blue-500 focus:border-blue-500"
              placeholder="Client pour Claude.ai production"
            />
          </div>

          <!-- Redirect URI -->
          <div>
            <label for="oauth2-redirect-uri" class="block text-sm font-medium text-gray-700 mb-1">
              Redirect URI
            </label>
            <input
              id="oauth2-redirect-uri"
              v-model="form.redirect_uri"
              type="url"
              class="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:ring-blue-500 focus:border-blue-500"
              placeholder="https://claude.ai/api/mcp/auth_callback"
            />
            <p class="text-xs text-gray-400 mt-1">
              URL de callback OAuth2 du client MCP (par défaut : Claude.ai)
            </p>
          </div>

          <!-- Drag-and-drop panel -->
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-2">
              Serveurs et outils autorisés
            </label>
            <DragDropPanel :drag-drop="dragDrop" />
          </div>

          <!-- TTL -->
          <div>
            <label for="oauth2-ttl" class="block text-sm font-medium text-gray-700 mb-1">
              Durée de vie du token d'accès (TTL)
            </label>
            <select
              id="oauth2-ttl"
              v-model="form.access_token_ttl"
              class="w-full border border-gray-300 rounded-md px-3 py-2 text-sm"
            >
              <option :value="3600">1 heure</option>
              <option :value="21600">6 heures</option>
              <option :value="86400">24 heures</option>
              <option :value="604800">7 jours</option>
              <option :value="2592000">30 jours</option>
            </select>
          </div>

          <!-- Expiration -->
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-2">Expiration du client</label>
            <div class="flex items-center gap-4 mb-2">
              <label class="flex items-center gap-2 cursor-pointer">
                <input
                  v-model="expirationType"
                  type="radio"
                  value="permanent"
                  class="text-blue-600"
                />
                <span class="text-sm">Permanent</span>
              </label>
              <label class="flex items-center gap-2 cursor-pointer">
                <input
                  v-model="expirationType"
                  type="radio"
                  value="custom"
                  class="text-blue-600"
                />
                <span class="text-sm">Expiration personnalisée</span>
              </label>
            </div>
            <input
              v-if="expirationType === 'custom'"
              v-model="form.expires_at"
              type="datetime-local"
              class="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:ring-blue-500 focus:border-blue-500"
            />
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
              {{ client ? 'Enregistrer les modifications' : 'Générer les identifiants' }}
            </button>
          </div>
        </form>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { oauth2Api } from '@/api/oauth2'
import { useServersStore } from '@/stores/servers'
import { useToast } from '@/composables/useToast'
import { useClipboard } from '@/composables/useClipboard'
import { useDragDrop } from '@/composables/useDragDrop'
import DragDropPanel from '@/components/shared/DragDropPanel.vue'
import type { OAuth2Client, CreateOAuth2ClientRequest } from '@/types/oauth2'

const props = defineProps<{ client?: OAuth2Client }>()
const emit = defineEmits<{ close: []; saved: [] }>()

const serversStore = useServersStore()
const toast = useToast()
const clipboard = useClipboard()
const dragDrop = useDragDrop()

const submitting = ref(false)
const expirationType = ref<'permanent' | 'custom'>(props.client?.expires_at ? 'custom' : 'permanent')
const createdClient = ref<OAuth2Client | null>(null)

const form = reactive({
  name: props.client?.name ?? '',
  description: props.client?.description ?? '',
  redirect_uri: props.client?.redirect_uris?.[0] ?? 'https://claude.ai/api/mcp/auth_callback',
  access_token_ttl: props.client?.access_token_ttl ?? 86400,
  expires_at: props.client?.expires_at ?? ''
})

const gatewayMcpUrl = computed(() => {
  return window.location.origin + '/mcp'
})

const tokenEndpointUrl = computed(() => {
  return window.location.origin + '/token'
})

onMounted(async () => {
  if (!serversStore.servers.length) {
    await serversStore.fetchServers()
  }
  if (props.client) {
    dragDrop.initWithSelection(
      serversStore.servers,
      props.client.server_ids,
      props.client.server_tools
    )
  } else {
    dragDrop.init(serversStore.servers)
  }
})

function handleClose() {
  if (!createdClient.value) {
    emit('close')
  }
}

async function handleSubmit() {
  submitting.value = true
  try {
    const serverIds = dragDrop.getServerIds()
    const serverTools = dragDrop.getServerTools()

    const data: CreateOAuth2ClientRequest = {
      name: form.name,
      description: form.description || undefined,
      redirect_uris: form.redirect_uri ? [form.redirect_uri] : undefined,
      server_ids: serverIds,
      server_tools: serverTools.length ? serverTools : undefined,
      access_token_ttl: form.access_token_ttl,
      expires_at: expirationType.value === 'custom' && form.expires_at
        ? new Date(form.expires_at).toISOString()
        : undefined
    }

    if (props.client) {
      await oauth2Api.update(props.client.id, data)
      toast.success('Client mis à jour')
      emit('saved')
    } else {
      const result = await oauth2Api.create(data)
      createdClient.value = result
    }
  } catch (err) {
    toast.error(err instanceof Error ? err.message : 'Erreur lors de la création du client')
  } finally {
    submitting.value = false
  }
}
</script>
