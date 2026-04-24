<template>
  <div>
    <!-- Page header (full width) -->
    <div class="mb-6 flex items-center gap-4">
      <button
        type="button"
        class="inline-flex items-center gap-1.5 text-sm text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white"
        @click="router.push('/oauth2')"
      >
        <i class="pi pi-arrow-left text-xs" />
        Retour
      </button>
      <h1 class="text-2xl font-bold text-gray-900 dark:text-white">
        {{ isEdit ? 'Modifier le client OAuth2' : 'Nouveau client OAuth2' }}
      </h1>
    </div>

    <div class="max-w-3xl mx-auto">

    <!-- Post-creation display -->
    <template v-if="createdClient">
      <!-- Warning -->
      <div class="flex items-start gap-3 p-4 mb-4 bg-warning-50 dark:bg-warning-500/15 border border-warning-200 dark:border-warning-500/30 rounded-lg">
        <i class="pi pi-exclamation-triangle text-warning-600 dark:text-warning-400 mt-0.5" />
        <p class="text-sm text-warning-800 dark:text-warning-400">
          Copiez ces identifiants maintenant — le secret ne sera plus affiché !
        </p>
      </div>

      <!-- Client ID -->
      <div class="mb-4">
        <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Client ID</label>
        <div class="flex items-center gap-2">
          <code class="flex-1 text-sm bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-800 rounded-md p-3 font-mono break-all select-all text-gray-800 dark:text-gray-300">
            {{ createdClient.id }}
          </code>
          <button
            class="shrink-0 p-2 rounded hover:bg-gray-100 dark:hover:bg-white/5 text-brand-500"
            title="Copier le Client ID"
            @click="clipboard.copy(createdClient!.id, 'Client ID')"
          >
            <i class="pi pi-copy" />
          </button>
        </div>
      </div>

      <!-- Client Secret -->
      <div class="mb-4">
        <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Client Secret</label>
        <div class="flex items-center gap-2">
          <code class="flex-1 text-sm bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-800 rounded-md p-3 font-mono break-all select-all text-gray-800 dark:text-gray-300">
            {{ createdClient.client_secret || 'Non disponible' }}
          </code>
          <button
            v-if="createdClient.client_secret"
            class="shrink-0 p-2 rounded hover:bg-gray-100 dark:hover:bg-white/5 text-brand-500"
            title="Copier le Client Secret"
            @click="clipboard.copy(createdClient!.client_secret || '', 'Client Secret')"
          >
            <i class="pi pi-copy" />
          </button>
        </div>
      </div>

      <!-- Config box -->
      <div class="p-4 mb-4 bg-brand-50 dark:bg-brand-500/10 border border-brand-200 dark:border-brand-500/30 rounded-lg">
        <h3 class="text-sm font-semibold text-brand-800 dark:text-brand-300 mb-2">Configuration Claude.ai</h3>
        <div class="space-y-2 text-sm">
          <div class="flex items-center gap-2">
            <span class="text-brand-600 dark:text-brand-400 font-medium">Gateway URL :</span>
            <code class="bg-white dark:bg-gray-900 px-2 py-0.5 rounded text-brand-900 dark:text-brand-300 font-mono text-xs">
              {{ gatewayMcpUrl }}
            </code>
            <button
              class="p-1 rounded hover:bg-brand-100 dark:hover:bg-brand-500/20 text-brand-600 dark:text-brand-400"
              @click="clipboard.copy(gatewayMcpUrl, 'Gateway URL')"
            >
              <i class="pi pi-copy text-xs" />
            </button>
          </div>
          <div class="flex items-center gap-2">
            <span class="text-brand-600 dark:text-brand-400 font-medium">Token endpoint :</span>
            <code class="bg-white dark:bg-gray-900 px-2 py-0.5 rounded text-brand-900 dark:text-brand-300 font-mono text-xs">
              {{ tokenEndpointUrl }}
            </code>
            <button
              class="p-1 rounded hover:bg-brand-100 dark:hover:bg-brand-500/20 text-brand-600 dark:text-brand-400"
              @click="clipboard.copy(tokenEndpointUrl, 'Token endpoint')"
            >
              <i class="pi pi-copy text-xs" />
            </button>
          </div>
        </div>
      </div>

      <!-- Back button -->
      <div class="flex justify-end pt-4 border-t border-gray-100 dark:border-gray-800">
        <button
          class="px-4 py-2 text-sm font-medium text-white bg-brand-500 rounded-md hover:bg-brand-600"
          @click="router.push('/oauth2')"
        >
          Retour aux clients
        </button>
      </div>
    </template>

    <!-- Loading state (edit mode) -->
    <div v-else-if="loading" class="flex items-center justify-center py-20">
      <i class="pi pi-spinner pi-spin text-2xl text-gray-400 dark:text-gray-500" />
    </div>

    <!-- Step form -->
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
          <!-- Name -->
          <div>
            <label for="form-name" class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Nom <span class="text-red-500">*</span>
            </label>
            <input
              id="form-name"
              v-model="form.name"
              type="text"
              class="h-11 w-full rounded-lg border border-gray-300 bg-transparent px-4 py-2.5 text-sm text-gray-800 shadow-theme-xs placeholder:text-gray-400 focus:border-brand-300 focus:outline-hidden focus:ring-3 focus:ring-brand-500/10 dark:border-gray-700 dark:bg-gray-900 dark:text-white/90 dark:placeholder:text-white/30"
              placeholder="claude-ai-prod"
            />
          </div>

          <!-- Description -->
          <div>
            <label for="form-desc" class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Description
            </label>
            <input
              id="form-desc"
              v-model="form.description"
              type="text"
              class="h-11 w-full rounded-lg border border-gray-300 bg-transparent px-4 py-2.5 text-sm text-gray-800 shadow-theme-xs placeholder:text-gray-400 focus:border-brand-300 focus:outline-hidden focus:ring-3 focus:ring-brand-500/10 dark:border-gray-700 dark:bg-gray-900 dark:text-white/90 dark:placeholder:text-white/30"
              placeholder="Client pour Claude.ai production"
            />
          </div>

          <!-- Redirect URI -->
          <div>
            <label for="form-redirect-uri" class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Redirect URI
            </label>
            <input
              id="form-redirect-uri"
              v-model="form.redirect_uri"
              type="url"
              class="h-11 w-full rounded-lg border border-gray-300 bg-transparent px-4 py-2.5 text-sm text-gray-800 shadow-theme-xs placeholder:text-gray-400 focus:border-brand-300 focus:outline-hidden focus:ring-3 focus:ring-brand-500/10 dark:border-gray-700 dark:bg-gray-900 dark:text-white/90 dark:placeholder:text-white/30"
              placeholder="https://claude.ai/api/mcp/auth_callback"
            />
            <p class="text-xs text-gray-400 dark:text-gray-500 mt-1">
              URL de callback OAuth2 du client MCP (par défaut : Claude.ai)
            </p>
          </div>
        </div>

        <!-- Section 2: Serveurs et outils -->
        <div v-show="isEdit || currentStep === 1" :class="isEdit ? 'mt-6 pt-6 border-t border-gray-100 dark:border-gray-800' : ''">
          <h3 v-if="isEdit" class="text-sm font-semibold text-gray-900 dark:text-white mb-3">Serveurs et outils</h3>
          <label v-else class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
            Serveurs et outils autorisés
          </label>
          <DragDropPanel
            v-if="dragDropReady"
            :initial-available="dragDrop.available.value"
            :initial-selected="dragDrop.selected.value"
            @update:available="v => dragDrop.available.value = v"
            @update:selected="v => dragDrop.selected.value = v"
          />
        </div>

        <!-- Section: Instructions LLM — dedicated tab, always shows every
             page with its server tags (renderability indicated inline). -->
        <div v-show="isEdit || currentStep === instructionsStepIndex" :class="isEdit ? 'mt-6 pt-6 border-t border-gray-100 dark:border-gray-800' : ''">
          <h3 v-if="isEdit" class="text-sm font-semibold text-gray-900 dark:text-white mb-3">Instructions LLM</h3>
          <InstructionsPicker
            v-model="form.instruction_ids"
            :server-ids="selectedServerIdsForPicker"
          />
        </div>

        <!-- Section 3: Acc\u00e8s Leexi (only when a Leexi server is selected) -->
        <div
          v-if="hasLeexiServer"
          v-show="isEdit || currentStep === leexiStepIndex"
          :class="isEdit ? 'mt-6 pt-6 border-t border-gray-100 dark:border-gray-800' : ''"
        >
          <h3 v-if="isEdit" class="text-sm font-semibold text-gray-900 dark:text-white mb-3">Acc&egrave;s Leexi</h3>
          <LeexiFilterPanel v-model="form.leexi_filter" />
        </div>

        <!-- Section 4: TTL, expiration et vérification -->
        <div v-show="isEdit || currentStep === expirationStepIndex" :class="isEdit ? 'mt-6 pt-6 border-t border-gray-100 dark:border-gray-800' : ''" class="space-y-4">
          <h3 v-if="isEdit" class="text-sm font-semibold text-gray-900 dark:text-white mb-3">TTL et expiration</h3>
          <!-- TTL -->
          <div>
            <label for="form-ttl" class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Durée de vie du token d'accès (TTL)
            </label>
            <select
              id="form-ttl"
              v-model="form.access_token_ttl"
              class="h-11 w-full rounded-lg border border-gray-300 bg-transparent px-4 py-2.5 text-sm text-gray-800 shadow-theme-xs focus:border-brand-300 focus:outline-hidden focus:ring-3 focus:ring-brand-500/10 dark:border-gray-700 dark:bg-gray-900 dark:text-white/90 appearance-none"
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
            <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">Expiration du client</label>
            <div class="flex items-center gap-4 mb-2">
              <label class="flex items-center gap-2 cursor-pointer">
                <input
                  v-model="expirationType"
                  type="radio"
                  value="permanent"
                  class="text-brand-500"
                />
                <span class="text-sm text-gray-800 dark:text-gray-200">Permanent</span>
              </label>
              <label class="flex items-center gap-2 cursor-pointer">
                <input
                  v-model="expirationType"
                  type="radio"
                  value="custom"
                  class="text-brand-500"
                />
                <span class="text-sm text-gray-800 dark:text-gray-200">Expiration personnalisée</span>
              </label>
            </div>
            <input
              v-if="expirationType === 'custom'"
              v-model="form.expires_at"
              type="datetime-local"
              class="h-11 w-full rounded-lg border border-gray-300 bg-transparent px-4 py-2.5 text-sm text-gray-800 shadow-theme-xs placeholder:text-gray-400 focus:border-brand-300 focus:outline-hidden focus:ring-3 focus:ring-brand-500/10 dark:border-gray-700 dark:bg-gray-900 dark:text-white/90 dark:placeholder:text-white/30"
            />
          </div>

          <!-- Summary (create mode only) -->
          <div v-if="!isEdit" class="border-t border-gray-100 dark:border-gray-800 pt-4">
            <h3 class="text-sm font-semibold text-gray-900 dark:text-white mb-3">Récapitulatif</h3>
            <dl class="divide-y divide-gray-100 dark:divide-gray-800">
              <div class="py-2 grid grid-cols-3 gap-4">
                <dt class="text-sm font-medium text-gray-500 dark:text-gray-400">Nom</dt>
                <dd class="text-sm text-gray-900 dark:text-white col-span-2">{{ form.name }}</dd>
              </div>
              <div v-if="form.description" class="py-2 grid grid-cols-3 gap-4">
                <dt class="text-sm font-medium text-gray-500 dark:text-gray-400">Description</dt>
                <dd class="text-sm text-gray-900 dark:text-white col-span-2">{{ form.description }}</dd>
              </div>
              <div class="py-2 grid grid-cols-3 gap-4">
                <dt class="text-sm font-medium text-gray-500 dark:text-gray-400">Redirect URI</dt>
                <dd class="text-sm text-gray-900 dark:text-white col-span-2 break-all">{{ form.redirect_uri }}</dd>
              </div>
              <div class="py-2 grid grid-cols-3 gap-4">
                <dt class="text-sm font-medium text-gray-500 dark:text-gray-400">Serveurs</dt>
                <dd class="text-sm text-gray-900 dark:text-white col-span-2">
                  {{ dragDrop.selectedCount.value.servers }} serveur(s), {{ dragDrop.selectedCount.value.tools }} outil(s)
                </dd>
              </div>
              <div class="py-2 grid grid-cols-3 gap-4">
                <dt class="text-sm font-medium text-gray-500 dark:text-gray-400">TTL token</dt>
                <dd class="text-sm text-gray-900 dark:text-white col-span-2">{{ ttlLabel }}</dd>
              </div>
              <div class="py-2 grid grid-cols-3 gap-4">
                <dt class="text-sm font-medium text-gray-500 dark:text-gray-400">Expiration</dt>
                <dd class="text-sm text-gray-900 dark:text-white col-span-2">
                  {{ expirationType === 'permanent' ? 'Permanent' : form.expires_at || 'Non définie' }}
                </dd>
              </div>
              <div v-if="hasLeexiServer" class="py-2 grid grid-cols-3 gap-4">
                <dt class="text-sm font-medium text-gray-500 dark:text-gray-400">Acc&egrave;s Leexi</dt>
                <dd class="text-sm text-gray-900 dark:text-white col-span-2">{{ leexiFilterSummary }}</dd>
              </div>
            </dl>
          </div>
        </div>
      </div>

      <!-- Edit mode: single submit -->
      <div v-if="isEdit" class="flex justify-end gap-3 mt-6">
        <button type="button" class="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-white/5 rounded-md hover:bg-gray-200 dark:hover:bg-gray-700" @click="router.push('/oauth2')">Annuler</button>
        <button type="button" class="px-4 py-2 text-sm font-medium text-white bg-brand-500 rounded-md hover:bg-brand-600 disabled:opacity-50" :disabled="submitting || !form.name.trim()" @click="handleSubmit">
          <i v-if="submitting" class="pi pi-spinner pi-spin mr-1" />
          Enregistrer
        </button>
      </div>

      <!-- Create mode: step navigation -->
      <div v-else class="flex justify-between mt-6">
        <button v-if="currentStep > 0" type="button" class="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-white/5 rounded-md hover:bg-gray-200 dark:hover:bg-gray-700" @click="goBack">Précédent</button>
        <div v-else />
        <div class="flex gap-3">
          <button type="button" class="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-white/5 rounded-md hover:bg-gray-200 dark:hover:bg-gray-700" @click="router.push('/oauth2')">Annuler</button>
          <button v-if="currentStep < lastStepIndex" type="button" class="px-4 py-2 text-sm font-medium text-white bg-brand-500 rounded-md hover:bg-brand-600 disabled:opacity-50" :disabled="!canGoNext" @click="goNext">Suivant</button>
          <button v-if="currentStep === lastStepIndex" type="button" class="px-4 py-2 text-sm font-medium text-white bg-brand-500 rounded-md hover:bg-brand-600 disabled:opacity-50" :disabled="submitting" @click="handleSubmit">
            <i v-if="submitting" class="pi pi-spinner pi-spin mr-1" />
            Générer les identifiants
          </button>
        </div>
      </div>
    </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { oauth2Api } from '@/api/oauth2'
import { useServersStore } from '@/stores/servers'
import { useToast } from '@/composables/useToast'
import { useClipboard } from '@/composables/useClipboard'
import { useDragDrop } from '@/composables/useDragDrop'
import StepTabs from '@/components/shared/StepTabs.vue'
import DragDropPanel from '@/components/shared/DragDropPanel.vue'
import LeexiFilterPanel from '@/components/tokens/LeexiFilterPanel.vue'
import InstructionsPicker from '@/components/llm-instructions/InstructionsPicker.vue'
import type { OAuth2Client, CreateOAuth2ClientRequest } from '@/types/oauth2'
import type { LeexiFilter } from '@/types/leexi'

const route = useRoute()
const router = useRouter()
const serversStore = useServersStore()
const toast = useToast()
const clipboard = useClipboard()
const dragDrop = useDragDrop()
const dragDropReady = ref(false)

// Step labels are dynamic: the "Acc\u00e8s Leexi" step is only shown when the
// selected servers include the Leexi backend (tool_prefix === 'leexi').
const stepLabels = computed(() => {
  const labels = ['Informations de base', 'Serveurs et outils', 'Instructions LLM']
  if (hasLeexiServer.value) labels.push('Acc\u00e8s Leexi')
  labels.push('TTL, expiration et vérification')
  return labels
})
const instructionsStepIndex = 2
const leexiStepIndex = computed(() => (hasLeexiServer.value ? 3 : -1))
const expirationStepIndex = computed(() => (hasLeexiServer.value ? 4 : 3))
const lastStepIndex = computed(() => stepLabels.value.length - 1)
const currentStep = ref(0)
const loading = ref(false)
const submitting = ref(false)
const expirationType = ref<'permanent' | 'custom'>('permanent')
const createdClient = ref<OAuth2Client | null>(null)

const isEdit = computed(() => !!route.params.id)

// hasLeexiServer is true when at least one selected server is the Leexi
// backend (identified by tool_prefix === 'leexi').
const hasLeexiServer = computed(() => {
  return dragDrop.selected.value.some(s => {
    const srv = serversStore.servers.find(x => x.id === s.id)
    return srv?.tool_prefix === 'leexi'
  })
})

const form = reactive({
  name: '',
  description: '',
  redirect_uri: 'https://claude.ai/api/mcp/auth_callback',
  access_token_ttl: 86400,
  expires_at: '',
  leexi_filter: { mode: 'none' } as LeexiFilter,
  instruction_ids: [] as string[]
})

const selectedServerIdsForPicker = computed(() => dragDrop.getServerIds())

const gatewayMcpUrl = computed(() => window.location.origin + '/mcp')
const tokenEndpointUrl = computed(() => window.location.origin + '/token')

const ttlOptions: Record<number, string> = {
  3600: '1 heure',
  21600: '6 heures',
  86400: '24 heures',
  604800: '7 jours',
  2592000: '30 jours'
}

const ttlLabel = computed(() => ttlOptions[form.access_token_ttl] || `${form.access_token_ttl}s`)

const leexiFilterSummary = computed(() => {
  const f = form.leexi_filter
  switch (f.mode) {
    case 'users':
      return `${(f.user_uuids || []).length} utilisateur(s)`
    case 'teams':
      return `${(f.team_uuids || []).length} \u00e9quipe(s)`
    case 'creator':
      return 'Cr\u00e9ateur du jeton uniquement'
    default:
      return 'Aucune restriction'
  }
})

const isStep1Valid = computed(() => !!form.name.trim())

const completedSteps = computed(() => {
  if (!isStep1Valid.value) return []
  return Array.from({ length: lastStepIndex.value }, (_, i) => i)
})

const canGoNext = computed(() => {
  if (currentStep.value === 0) return isStep1Valid.value
  return currentStep.value < lastStepIndex.value
})

// Snap back if the user removes the Leexi server while sitting on the
// (now-gone) Leexi step.
watch(hasLeexiServer, (has) => {
  if (!has && currentStep.value > lastStepIndex.value) {
    currentStep.value = lastStepIndex.value
  }
})

onMounted(async () => {
  try {
    await serversStore.fetchServers()
  } catch (err) {
    console.error('[ClientFormView] Failed to fetch servers:', err)
  }

  if (isEdit.value) {
    loading.value = true
    try {
      const client = await oauth2Api.get(route.params.id as string)
      form.name = client.name
      form.description = client.description ?? ''
      form.redirect_uri = client.redirect_uris?.[0] ?? 'https://claude.ai/api/mcp/auth_callback'
      form.access_token_ttl = client.access_token_ttl ?? 86400
      form.expires_at = client.expires_at ?? ''
      if (client.expires_at) {
        expirationType.value = 'custom'
      }
      if (client.leexi_filter) {
        form.leexi_filter = { ...client.leexi_filter }
      }
      if (client.instruction_ids) {
        form.instruction_ids = [...client.instruction_ids]
      }
      dragDrop.initWithSelection(
        serversStore.servers,
        client.server_ids,
        client.server_tools
      )
      dragDropReady.value = true
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Erreur lors du chargement du client')
      router.push('/oauth2')
    } finally {
      loading.value = false
    }
  } else {
    dragDrop.init(serversStore.servers)
    dragDropReady.value = true
  }
})

function goToStep(step: number) {
  if (step < currentStep.value || completedSteps.value.includes(step)) {
    currentStep.value = step
  }
}

function goNext() {
  if (canGoNext.value && currentStep.value < lastStepIndex.value) {
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

    const data: CreateOAuth2ClientRequest = {
      name: form.name,
      description: form.description || undefined,
      redirect_uris: form.redirect_uri ? [form.redirect_uri] : undefined,
      server_ids: serverIds,
      server_tools: serverTools.length ? serverTools : undefined,
      instruction_ids: form.instruction_ids.length ? [...form.instruction_ids] : undefined,
      access_token_ttl: form.access_token_ttl,
      expires_at: expirationType.value === 'custom' && form.expires_at
        ? new Date(form.expires_at).toISOString()
        : undefined,
      // Only send the filter when the Leexi server is in scope.
      leexi_filter: hasLeexiServer.value
        ? (form.leexi_filter.mode === 'none' ? { mode: 'none' } : form.leexi_filter)
        : { mode: 'none' }
    }

    if (isEdit.value) {
      await oauth2Api.update(route.params.id as string, data)
      toast.success('Client mis à jour')
      router.push('/oauth2')
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
