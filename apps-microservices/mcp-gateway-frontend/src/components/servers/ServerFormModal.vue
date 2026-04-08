<template>
  <div class="fixed inset-0 bg-black/50 z-40 flex items-center justify-center" @click.self="emit('close')">
    <div class="bg-white rounded-lg shadow-xl p-6 max-w-lg w-full max-h-[90vh] overflow-y-auto">
      <h2 class="text-lg font-semibold text-gray-900 mb-4">
        {{ server ? 'Modifier le serveur' : 'Ajouter un serveur' }}
      </h2>

      <form @submit.prevent="handleSubmit" class="space-y-4">
        <!-- Name -->
        <div>
          <label for="form-name" class="block text-sm font-medium text-gray-700 mb-1">
            Nom <span class="text-red-500">*</span>
          </label>
          <input
            id="form-name"
            v-model="form.name"
            type="text"
            required
            class="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:ring-blue-500 focus:border-blue-500"
            placeholder="Mon serveur MCP"
          />
        </div>

        <!-- Transport -->
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-2">Transport</label>
          <div class="flex items-center gap-4">
            <label class="flex items-center gap-2 cursor-pointer">
              <input
                v-model="form.mcp_transport"
                type="radio"
                value="http"
                class="text-blue-600"
              />
              <span class="text-sm">HTTP</span>
            </label>
            <label class="flex items-center gap-2 cursor-pointer">
              <input
                v-model="form.mcp_transport"
                type="radio"
                value="stdio"
                class="text-blue-600"
              />
              <span class="text-sm">Stdio</span>
            </label>
          </div>
        </div>

        <!-- HTTP fields -->
        <template v-if="form.mcp_transport === 'http'">
          <div>
            <label for="form-url" class="block text-sm font-medium text-gray-700 mb-1">
              URL <span class="text-red-500">*</span>
            </label>
            <input
              id="form-url"
              v-model="form.url"
              type="url"
              :required="form.mcp_transport === 'http'"
              class="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:ring-blue-500 focus:border-blue-500"
              placeholder="https://mcp-server.example.com"
            />
          </div>
          <div>
            <label for="form-transport" class="block text-sm font-medium text-gray-700 mb-1">
              Préférence de transport
            </label>
            <select
              id="form-transport"
              v-model="form.transport_preference"
              class="w-full border border-gray-300 rounded-md px-3 py-2 text-sm"
            >
              <option value="auto">Auto</option>
              <option value="sse">SSE</option>
              <option value="streamable-http">Streamable HTTP</option>
            </select>
          </div>
          <div>
            <label for="form-timeout" class="block text-sm font-medium text-gray-700 mb-1">
              Timeout (ms)
            </label>
            <input
              id="form-timeout"
              v-model.number="form.connect_timeout_ms"
              type="number"
              min="1000"
              class="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:ring-blue-500 focus:border-blue-500"
            />
          </div>
          <div>
            <label for="form-auth-headers" class="block text-sm font-medium text-gray-700 mb-1">
              En-têtes d'authentification (JSON)
            </label>
            <textarea
              id="form-auth-headers"
              v-model="authHeadersJson"
              rows="3"
              class="w-full border border-gray-300 rounded-md px-3 py-2 text-sm font-mono focus:ring-blue-500 focus:border-blue-500"
              placeholder='{"Authorization": "Bearer xxx"}'
            />
            <p v-if="authHeadersError" class="text-xs text-red-500 mt-1">{{ authHeadersError }}</p>
          </div>
        </template>

        <!-- Stdio fields -->
        <template v-if="form.mcp_transport === 'stdio'">
          <div>
            <label for="form-command" class="block text-sm font-medium text-gray-700 mb-1">
              Commande <span class="text-red-500">*</span>
            </label>
            <input
              id="form-command"
              v-model="form.mcp_command"
              type="text"
              :required="form.mcp_transport === 'stdio'"
              class="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:ring-blue-500 focus:border-blue-500"
              placeholder="npx"
            />
          </div>
          <div>
            <label for="form-args" class="block text-sm font-medium text-gray-700 mb-1">
              Arguments (un par ligne)
            </label>
            <textarea
              id="form-args"
              v-model="argsText"
              rows="3"
              class="w-full border border-gray-300 rounded-md px-3 py-2 text-sm font-mono focus:ring-blue-500 focus:border-blue-500"
              placeholder="-y&#10;@modelcontextprotocol/server-filesystem&#10;/path/to/dir"
            />
          </div>
          <div>
            <label for="form-env" class="block text-sm font-medium text-gray-700 mb-1">
              Variables d'environnement (JSON)
            </label>
            <textarea
              id="form-env"
              v-model="envJson"
              rows="3"
              class="w-full border border-gray-300 rounded-md px-3 py-2 text-sm font-mono focus:ring-blue-500 focus:border-blue-500"
              placeholder='{"API_KEY": "xxx"}'
            />
            <p v-if="envJsonError" class="text-xs text-red-500 mt-1">{{ envJsonError }}</p>
          </div>
        </template>

        <!-- Tags -->
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">Tags</label>
          <div class="flex flex-wrap gap-1 mb-2" v-if="form.tags.length">
            <span
              v-for="tag in form.tags"
              :key="tag"
              class="inline-flex items-center gap-1 text-xs bg-blue-100 text-blue-700 px-2 py-0.5 rounded-full"
            >
              {{ tag }}
              <button type="button" class="hover:text-blue-900" @click="removeTag(tag)">
                <i class="pi pi-times text-[10px]" />
              </button>
            </span>
          </div>
          <div class="relative">
            <input
              v-model="tagSearch"
              type="text"
              class="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:ring-blue-500 focus:border-blue-500"
              placeholder="Rechercher ou créer un tag..."
              @keydown.enter.prevent="addTagFromSearch"
              @keydown.escape="tagSearch = ''; showTagDropdown = false"
              @focus="showTagDropdown = true"
            />
            <div
              v-if="showTagDropdown && filteredTags.length"
              class="absolute z-10 mt-1 w-full bg-white border border-gray-200 rounded-md shadow-lg max-h-32 overflow-y-auto"
            >
              <button
                v-for="tag in filteredTags"
                :key="tag"
                type="button"
                class="w-full text-left px-3 py-1.5 text-sm hover:bg-gray-100"
                @click="addTag(tag)"
              >
                {{ tag }}
              </button>
            </div>
          </div>
        </div>

        <!-- Tool prefix -->
        <div>
          <label for="form-tool-prefix" class="block text-sm font-medium text-gray-700 mb-1">
            Préfixe d'outils
          </label>
          <input
            id="form-tool-prefix"
            v-model="form.tool_prefix"
            type="text"
            pattern="[a-zA-Z0-9]*"
            class="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:ring-blue-500 focus:border-blue-500"
            placeholder="myprefix"
          />
          <p class="text-xs text-gray-400 mt-1">Alphanumérique uniquement</p>
        </div>

        <!-- Auto-discover (create only) -->
        <div v-if="!server" class="flex items-center gap-2">
          <input
            id="form-discover"
            v-model="form.auto_discover"
            type="checkbox"
            class="rounded border-gray-300 text-blue-600"
          />
          <label for="form-discover" class="text-sm text-gray-700">
            Découvrir automatiquement les outils après création
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
            {{ server ? 'Enregistrer' : 'Créer' }}
          </button>
        </div>
      </form>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { useServersStore } from '@/stores/servers'
import { useToast } from '@/composables/useToast'
import type { Server, CreateServerRequest } from '@/types/server'

const props = defineProps<{ server?: Server }>()
const emit = defineEmits<{ close: []; saved: [] }>()

const serversStore = useServersStore()
const toast = useToast()

const submitting = ref(false)
const tagSearch = ref('')
const showTagDropdown = ref(false)
const authHeadersJson = ref('')
const authHeadersError = ref('')
const argsText = ref('')
const envJson = ref('')
const envJsonError = ref('')

const form = reactive<{
  name: string
  mcp_transport: string
  url: string
  transport_preference: string
  connect_timeout_ms: number
  mcp_command: string
  tags: string[]
  tool_prefix: string
  auto_discover: boolean
}>({
  name: props.server?.name ?? '',
  mcp_transport: props.server?.mcp_transport ?? 'http',
  url: props.server?.url ?? '',
  transport_preference: props.server?.transport_preference ?? 'auto',
  connect_timeout_ms: props.server?.connect_timeout_ms ?? 10000,
  mcp_command: props.server?.mcp_command ?? '',
  tags: props.server?.tags ? [...props.server.tags] : [],
  tool_prefix: props.server?.tool_prefix ?? '',
  auto_discover: true
})

onMounted(() => {
  if (props.server) {
    if (props.server.mcp_args?.length) {
      argsText.value = props.server.mcp_args.join('\n')
    }
    if (props.server.mcp_env) {
      envJson.value = JSON.stringify(props.server.mcp_env, null, 2)
    }
  }
  serversStore.fetchTags()
})

const filteredTags = computed(() => {
  const q = tagSearch.value.toLowerCase()
  return serversStore.tags
    .filter(t => !form.tags.includes(t))
    .filter(t => !q || t.toLowerCase().includes(q))
})

function addTag(tag: string) {
  if (!form.tags.includes(tag)) {
    form.tags.push(tag)
  }
  tagSearch.value = ''
  showTagDropdown.value = false
}

function removeTag(tag: string) {
  form.tags = form.tags.filter(t => t !== tag)
}

function addTagFromSearch() {
  const tag = tagSearch.value.trim()
  if (tag && !form.tags.includes(tag)) {
    form.tags.push(tag)
  }
  tagSearch.value = ''
  showTagDropdown.value = false
}

function parseJsonField(value: string, errorRef: { value: string }): Record<string, string> | undefined {
  if (!value.trim()) return undefined
  try {
    const parsed = JSON.parse(value)
    errorRef.value = ''
    return parsed
  } catch {
    errorRef.value = 'JSON invalide'
    return undefined
  }
}

async function handleSubmit() {
  submitting.value = true
  try {
    const data: CreateServerRequest = {
      name: form.name,
      mcp_transport: form.mcp_transport,
      tags: form.tags.length ? form.tags : undefined,
      tool_prefix: form.tool_prefix || undefined
    }

    if (form.mcp_transport === 'http') {
      data.url = form.url
      data.transport_preference = form.transport_preference
      data.connect_timeout_ms = form.connect_timeout_ms
      const headers = parseJsonField(authHeadersJson.value, authHeadersError)
      if (authHeadersError.value) return
      if (headers) data.auth_headers = headers
    } else {
      data.mcp_command = form.mcp_command
      if (argsText.value.trim()) {
        data.mcp_args = argsText.value.split('\n').map(l => l.trim()).filter(Boolean)
      }
      const env = parseJsonField(envJson.value, envJsonError)
      if (envJsonError.value) return
      if (env) data.mcp_env = env
    }

    if (props.server) {
      await serversStore.updateServer(props.server.id, data)
    } else {
      data.auto_discover = form.auto_discover
      await serversStore.createServer(data)
    }

    emit('saved')
  } catch (err) {
    toast.error(err instanceof Error ? err.message : 'Erreur lors de l\'enregistrement')
  } finally {
    submitting.value = false
  }
}
</script>
