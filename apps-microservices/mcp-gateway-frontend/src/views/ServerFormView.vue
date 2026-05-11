<template>
  <div>
    <!-- Page header (full width) -->
    <div class="mb-6 flex items-center gap-4">
      <BaseButton variant="ghost" size="sm" @click="router.push('/servers')">
        <i class="pi pi-arrow-left text-xs mr-1" />
        Retour
      </BaseButton>
      <h1 class="text-2xl font-bold text-gray-900 dark:text-white">
        {{ isEdit ? 'Modifier le serveur' : 'Nouveau serveur' }}
      </h1>
    </div>

    <div class="max-w-3xl mx-auto">

    <!-- Loading state (edit mode) -->
    <div v-if="loading" class="flex items-center justify-center py-20">
      <i class="pi pi-spinner pi-spin text-2xl text-gray-400 dark:text-gray-500" />
    </div>

    <template v-else>
      <!-- Step tabs (create mode only) -->
      <StepTabs
        v-if="!isEdit"
        :steps="stepLabels"
        :current-step="currentStep"
        :completed-steps="completedSteps"
        @update:current-step="goToStep"
      />

      <!-- Form content -->
      <div class="bg-white dark:bg-gray-900 rounded-lg shadow-theme-xs border border-gray-200 dark:border-gray-800 p-6">
        <!-- Section 1: Informations de base -->
        <div v-show="isEdit || currentStep === 0" class="space-y-4">
          <h3 v-if="isEdit" class="text-sm font-semibold text-gray-900 dark:text-white mb-3">Informations de base</h3>
          <FormField label="Nom" required>
            <template #default="{ id }">
              <BaseInput :id="id" v-model="form.name" placeholder="Mon serveur MCP" />
            </template>
          </FormField>

          <div>
            <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">Transport</label>
            <div class="flex items-center gap-4">
              <label class="flex items-center gap-2 cursor-pointer">
                <input v-model="form.mcp_transport" type="radio" value="http" class="text-brand-500" />
                <span class="text-sm text-gray-800 dark:text-gray-200">HTTP</span>
              </label>
              <label class="flex items-center gap-2 cursor-pointer">
                <input v-model="form.mcp_transport" type="radio" value="stdio" class="text-brand-500" />
                <span class="text-sm text-gray-800 dark:text-gray-200">Stdio</span>
              </label>
            </div>
          </div>

          <template v-if="form.mcp_transport === 'http'">
            <FormField label="URL" required>
              <template #default="{ id }">
                <BaseInput :id="id" v-model="form.url" type="url" placeholder="https://mcp-server.example.com" />
              </template>
            </FormField>
            <FormField label="Préférence de transport">
              <template #default="{ id }">
                <BaseSelect :id="id" v-model="form.transport_preference">
                  <option value="auto">Auto</option>
                  <option value="sse">SSE</option>
                  <option value="streamable-http">Streamable HTTP</option>
                </BaseSelect>
              </template>
            </FormField>
            <FormField label="Timeout (ms)">
              <template #default="{ id }">
                <BaseInput :id="id" v-model.number="form.connect_timeout_ms" type="number" />
              </template>
            </FormField>
            <FormField label="En-têtes d'authentification (JSON)" :error="authHeadersError">
              <template #default="{ id }">
                <BaseTextarea :id="id" v-model="authHeadersJson" :rows="3" monospace placeholder='{"Authorization": "Bearer xxx"}' />
              </template>
            </FormField>
          </template>

          <template v-if="form.mcp_transport === 'stdio'">
            <FormField label="Commande" required>
              <template #default="{ id }">
                <BaseInput :id="id" v-model="form.mcp_command" placeholder="npx" />
              </template>
            </FormField>
            <FormField label="Arguments (un par ligne)">
              <template #default="{ id }">
                <BaseTextarea :id="id" v-model="argsText" :rows="3" monospace placeholder="-y&#10;@modelcontextprotocol/server-filesystem&#10;/path/to/dir" />
              </template>
            </FormField>
            <FormField label="Variables d'environnement (JSON)" :error="envJsonError">
              <template #default="{ id }">
                <BaseTextarea :id="id" v-model="envJson" :rows="3" monospace placeholder='{"API_KEY": "xxx"}' />
              </template>
            </FormField>
          </template>
        </div>

        <!-- Section 2: Tags et configuration -->
        <div v-show="isEdit || currentStep === 1" :class="isEdit ? 'mt-6 pt-6 border-t border-gray-100 dark:border-gray-800' : ''" class="space-y-4">
          <h3 v-if="isEdit" class="text-sm font-semibold text-gray-900 dark:text-white mb-3">Tags et configuration</h3>
          <!-- Tags -->
          <div>
            <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Tags</label>
            <div class="flex flex-wrap gap-1 mb-2" v-if="form.tags.length">
              <span
                v-for="tag in form.tags"
                :key="tag"
                class="inline-flex items-center gap-1 text-xs bg-brand-100 dark:bg-brand-500/20 text-brand-700 dark:text-brand-400 px-2 py-0.5 rounded-full"
              >
                {{ tag }}
                <button type="button" class="hover:text-brand-900 dark:hover:text-brand-300" @click="removeTag(tag)">
                  <i class="pi pi-times text-[10px]" />
                </button>
              </span>
            </div>
            <div class="relative">
              <BaseInput
                v-model="tagSearch"
                placeholder="Rechercher ou créer un tag..."
                @keydown.enter.prevent="addTagFromSearch"
                @keydown.escape="tagSearch = ''; showTagDropdown = false"
                @focus="showTagDropdown = true"
              />
              <div
                v-if="showTagDropdown && filteredTags.length"
                class="absolute z-10 mt-1 w-full bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-md shadow-theme-lg max-h-32 overflow-y-auto"
              >
                <button
                  v-for="tag in filteredTags"
                  :key="tag"
                  type="button"
                  class="w-full text-left px-3 py-1.5 text-sm hover:bg-gray-100 dark:hover:bg-white/5 text-gray-800 dark:text-gray-200"
                  @click="addTag(tag)"
                >
                  {{ tag }}
                </button>
              </div>
            </div>
          </div>

          <!-- Icon picker -->
          <IconPicker v-model="form.icon" />

          <FormField label="Préfixe d'outils" hint="Alphanumérique uniquement">
            <template #default="{ id }">
              <BaseInput :id="id" v-model="form.tool_prefix" placeholder="myprefix" pattern="[a-zA-Z0-9]*" />
            </template>
          </FormField>

          <!-- Auto-discover (create only) -->
          <div v-if="!isEdit" class="flex items-center gap-2">
            <input
              id="form-discover"
              v-model="form.auto_discover"
              type="checkbox"
              class="rounded border-gray-300 text-brand-500 dark:border-gray-700"
            />
            <label for="form-discover" class="text-sm text-gray-700 dark:text-gray-300">
              Découvrir automatiquement les outils après création
            </label>
          </div>
        </div>

        <!-- Step 3: Vérification (create mode only) -->
        <div v-if="!isEdit" v-show="currentStep === 2" class="space-y-4">
          <h3 class="text-sm font-semibold text-gray-900 dark:text-white mb-3">Récapitulatif</h3>

          <dl class="divide-y divide-gray-100 dark:divide-gray-800">
            <!-- Name -->
            <div class="py-2 grid grid-cols-3 gap-4">
              <dt class="text-sm font-medium text-gray-500 dark:text-gray-400">Nom</dt>
              <dd class="text-sm text-gray-900 dark:text-white col-span-2">{{ form.name }}</dd>
            </div>

            <!-- Transport -->
            <div class="py-2 grid grid-cols-3 gap-4">
              <dt class="text-sm font-medium text-gray-500 dark:text-gray-400">Transport</dt>
              <dd class="text-sm text-gray-900 dark:text-white col-span-2">{{ form.mcp_transport.toUpperCase() }}</dd>
            </div>

            <!-- HTTP-specific -->
            <template v-if="form.mcp_transport === 'http'">
              <div class="py-2 grid grid-cols-3 gap-4">
                <dt class="text-sm font-medium text-gray-500 dark:text-gray-400">URL</dt>
                <dd class="text-sm text-gray-900 dark:text-white col-span-2 break-all">{{ form.url }}</dd>
              </div>
              <div class="py-2 grid grid-cols-3 gap-4">
                <dt class="text-sm font-medium text-gray-500 dark:text-gray-400">Préférence</dt>
                <dd class="text-sm text-gray-900 dark:text-white col-span-2">{{ form.transport_preference }}</dd>
              </div>
              <div class="py-2 grid grid-cols-3 gap-4">
                <dt class="text-sm font-medium text-gray-500 dark:text-gray-400">Timeout</dt>
                <dd class="text-sm text-gray-900 dark:text-white col-span-2">{{ form.connect_timeout_ms }} ms</dd>
              </div>
              <div v-if="authHeadersJson.trim()" class="py-2 grid grid-cols-3 gap-4">
                <dt class="text-sm font-medium text-gray-500 dark:text-gray-400">En-têtes auth</dt>
                <dd class="text-sm text-gray-900 dark:text-white col-span-2 font-mono text-xs whitespace-pre-wrap">{{ authHeadersJson }}</dd>
              </div>
            </template>

            <!-- Stdio-specific -->
            <template v-if="form.mcp_transport === 'stdio'">
              <div class="py-2 grid grid-cols-3 gap-4">
                <dt class="text-sm font-medium text-gray-500 dark:text-gray-400">Commande</dt>
                <dd class="text-sm text-gray-900 dark:text-white col-span-2 font-mono">{{ form.mcp_command }}</dd>
              </div>
              <div v-if="argsText.trim()" class="py-2 grid grid-cols-3 gap-4">
                <dt class="text-sm font-medium text-gray-500 dark:text-gray-400">Arguments</dt>
                <dd class="text-sm text-gray-900 dark:text-white col-span-2 font-mono text-xs whitespace-pre-wrap">{{ argsText }}</dd>
              </div>
              <div v-if="envJson.trim()" class="py-2 grid grid-cols-3 gap-4">
                <dt class="text-sm font-medium text-gray-500 dark:text-gray-400">Variables env</dt>
                <dd class="text-sm text-gray-900 dark:text-white col-span-2 font-mono text-xs whitespace-pre-wrap">{{ envJson }}</dd>
              </div>
            </template>

            <!-- Tags -->
            <div class="py-2 grid grid-cols-3 gap-4">
              <dt class="text-sm font-medium text-gray-500 dark:text-gray-400">Tags</dt>
              <dd class="text-sm text-gray-900 dark:text-white col-span-2">
                <div v-if="form.tags.length" class="flex flex-wrap gap-1">
                  <span
                    v-for="tag in form.tags"
                    :key="tag"
                    class="inline-flex text-xs bg-brand-100 dark:bg-brand-500/20 text-brand-700 dark:text-brand-400 px-2 py-0.5 rounded-full"
                  >
                    {{ tag }}
                  </span>
                </div>
                <span v-else class="text-gray-400 dark:text-gray-500 italic">Aucun</span>
              </dd>
            </div>

            <!-- Icon -->
            <div v-if="form.icon" class="py-2 grid grid-cols-3 gap-4">
              <dt class="text-sm font-medium text-gray-500 dark:text-gray-400">Icone</dt>
              <dd class="col-span-2">
                <img :src="form.icon" alt="Icon" class="w-8 h-8 rounded border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 object-contain p-0.5" />
              </dd>
            </div>

            <!-- Tool prefix -->
            <div v-if="form.tool_prefix" class="py-2 grid grid-cols-3 gap-4">
              <dt class="text-sm font-medium text-gray-500 dark:text-gray-400">Préfixe d'outils</dt>
              <dd class="text-sm text-gray-900 dark:text-white col-span-2 font-mono">{{ form.tool_prefix }}</dd>
            </div>

            <!-- Auto-discover (create only) -->
            <div v-if="!isEdit" class="py-2 grid grid-cols-3 gap-4">
              <dt class="text-sm font-medium text-gray-500 dark:text-gray-400">Auto-découverte</dt>
              <dd class="text-sm text-gray-900 dark:text-white col-span-2">{{ form.auto_discover ? 'Oui' : 'Non' }}</dd>
            </div>
          </dl>
        </div>
      </div>

      <!-- Edit mode: single submit -->
      <div v-if="isEdit" class="flex justify-end gap-3 mt-6">
        <BaseButton variant="secondary" @click="router.push('/servers')">Annuler</BaseButton>
        <BaseButton :disabled="!isStep1Valid" :loading="submitting" @click="handleSubmit">Enregistrer</BaseButton>
      </div>

      <!-- Create mode: step navigation -->
      <div v-else class="flex justify-between mt-6">
        <BaseButton v-if="currentStep > 0" variant="secondary" @click="goBack">Précédent</BaseButton>
        <div v-else />

        <div class="flex gap-3">
          <BaseButton variant="secondary" @click="router.push('/servers')">Annuler</BaseButton>
          <BaseButton v-if="currentStep < 2" :disabled="!canGoNext" @click="goNext">Suivant</BaseButton>
          <BaseButton v-if="currentStep === 2" :loading="submitting" @click="handleSubmit">Créer</BaseButton>
        </div>
      </div>
    </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useServersStore } from '@/stores/servers'
import { useToast } from '@/composables/useToast'
import { serversApi } from '@/api/servers'
import StepTabs from '@/components/shared/StepTabs.vue'
import IconPicker from '@/components/servers/IconPicker.vue'
import BaseInput from '@/components/ui/BaseInput.vue'
import BaseTextarea from '@/components/ui/BaseTextarea.vue'
import BaseSelect from '@/components/ui/BaseSelect.vue'
import BaseButton from '@/components/ui/BaseButton.vue'
import FormField from '@/components/ui/FormField.vue'
import { toErrorMessage } from '@/utils/error'
import type { CreateServerRequest } from '@/types/server'

const route = useRoute()
const router = useRouter()
const serversStore = useServersStore()
const toast = useToast()

const stepLabels = ['Informations de base', 'Tags et configuration', 'Vérification']
const currentStep = ref(0)
const loading = ref(false)
const submitting = ref(false)
const tagSearch = ref('')
const showTagDropdown = ref(false)
const authHeadersJson = ref('')
const authHeadersError = ref('')
const argsText = ref('')
const envJson = ref('')
const envJsonError = ref('')

const isEdit = computed(() => !!route.params.id)

const form = reactive<{
  name: string
  mcp_transport: string
  url: string
  transport_preference: string
  connect_timeout_ms: number
  mcp_command: string
  tags: string[]
  tool_prefix: string
  icon: string
  auto_discover: boolean
}>({
  name: '',
  mcp_transport: 'http',
  url: '',
  transport_preference: 'auto',
  connect_timeout_ms: 10000,
  mcp_command: '',
  tags: [],
  tool_prefix: '',
  icon: '',
  auto_discover: true
})

const completedSteps = computed(() => {
  const completed: number[] = []
  if (isStep1Valid.value) completed.push(0)
  if (isStep1Valid.value) completed.push(1)
  return completed
})

const isStep1Valid = computed(() => {
  if (!form.name.trim()) return false
  if (form.mcp_transport === 'http' && !form.url.trim()) return false
  if (form.mcp_transport === 'stdio' && !form.mcp_command.trim()) return false
  return true
})

const canGoNext = computed(() => {
  if (currentStep.value === 0) return isStep1Valid.value
  if (currentStep.value === 1) return true
  return false
})

const filteredTags = computed(() => {
  const q = tagSearch.value.toLowerCase()
  return serversStore.tags
    .filter(t => !form.tags.includes(t))
    .filter(t => !q || t.toLowerCase().includes(q))
})

onMounted(async () => {
  serversStore.fetchTags()

  if (isEdit.value) {
    loading.value = true
    try {
      const server = await serversApi.get(route.params.id as string)
      form.name = server.name
      form.mcp_transport = server.mcp_transport || 'http'
      form.url = server.url || ''
      form.transport_preference = server.transport_preference || 'auto'
      form.connect_timeout_ms = server.connect_timeout_ms || 10000
      form.mcp_command = server.mcp_command || ''
      form.tags = server.tags ? [...server.tags] : []
      form.tool_prefix = server.tool_prefix || ''
      form.icon = server.icon || ''

      if (server.mcp_args?.length) {
        argsText.value = server.mcp_args.join('\n')
      }
      if (server.mcp_env) {
        envJson.value = JSON.stringify(server.mcp_env, null, 2)
      }
    } catch (err) {
      toast.error(toErrorMessage(err, 'Erreur lors du chargement du serveur'))
      router.push('/servers')
    } finally {
      loading.value = false
    }
  } else {
    // Default icon for a brand-new custom MCP server. Users can change it in
    // the IconPicker; stays empty on servers that predate this default.
    form.icon = '/images/servers/hp-logo.svg'
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
      tool_prefix: form.tool_prefix || undefined,
      icon: form.icon || undefined
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

    if (isEdit.value) {
      await serversStore.updateServer(route.params.id as string, data)
    } else {
      data.auto_discover = form.auto_discover
      await serversStore.createServer(data)
    }

    toast.success(isEdit.value ? 'Serveur modifié' : 'Serveur créé')
    router.push('/servers')
  } catch (err) {
    toast.error(toErrorMessage(err, 'Erreur lors de l\'enregistrement'))
  } finally {
    submitting.value = false
  }
}
</script>
