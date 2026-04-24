<template>
  <div>
    <!-- Page header (full width) -->
    <div class="mb-6 flex items-center gap-4">
      <button
        type="button"
        class="inline-flex items-center gap-1.5 text-sm text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white"
        @click="router.push('/tokens')"
      >
        <i class="pi pi-arrow-left text-xs" />
        Retour
      </button>
      <h1 class="text-2xl font-bold text-gray-900 dark:text-white">
        {{ isEdit ? 'Modifier le jeton' : 'Nouveau jeton' }}
      </h1>
    </div>

    <div class="max-w-3xl mx-auto">

    <!-- Loading state (edit mode) -->
    <div v-if="loading" class="flex items-center justify-center py-20">
      <i class="pi pi-spinner pi-spin text-2xl text-gray-400 dark:text-gray-500" />
    </div>

    <!-- Post-creation display -->
    <div v-else-if="createdToken" class="space-y-6">
      <!-- Warning banner -->
      <div class="rounded-lg border border-warning-300 dark:border-warning-500/30 bg-warning-50 dark:bg-warning-500/15 p-4">
        <div class="flex items-start gap-3">
          <i class="pi pi-exclamation-triangle text-warning-600 dark:text-warning-400 mt-0.5" />
          <p class="text-sm font-medium text-warning-800 dark:text-warning-400">
            Copiez ce jeton maintenant — il ne sera plus affich&eacute; !
          </p>
        </div>
      </div>

      <!-- Token value -->
      <div>
        <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">Jeton d'acc&egrave;s</label>
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
        <div class="flex items-center justify-between mb-2">
          <label class="block text-sm font-medium text-gray-700 dark:text-gray-300">Configuration .mcp.json</label>
          <a
            :href="`/install-guide/${form.mcp_command || ''}`"
            target="_blank"
            rel="noopener noreferrer"
            class="text-xs text-brand-500 hover:text-brand-600 flex items-center gap-1"
            title="Ouvrir le guide d'installation dans un nouvel onglet"
          >
            <i class="pi pi-external-link text-[10px]" />
            Documentation
          </a>
        </div>
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
          class="px-4 py-2 text-sm font-medium text-white bg-brand-500 rounded-md hover:bg-brand-600"
          @click="router.push('/tokens')"
        >
          Retour aux jetons
        </button>
      </div>
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
              placeholder="Mon jeton MCP"
            />
          </div>

          <!-- Description -->
          <div>
            <label for="form-description" class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Description
            </label>
            <textarea
              id="form-description"
              v-model="form.description"
              rows="2"
              class="w-full rounded-lg border border-gray-300 bg-transparent px-4 py-2.5 text-sm text-gray-800 shadow-theme-xs placeholder:text-gray-400 focus:border-brand-300 focus:outline-hidden focus:ring-3 focus:ring-brand-500/10 dark:border-gray-700 dark:bg-gray-900 dark:text-white/90 dark:placeholder:text-white/30"
              placeholder="Description optionnelle du jeton"
            />
          </div>

          <!-- Server name for .mcp.json -->
          <div>
            <label for="form-server-name" class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Nom du serveur (.mcp.json)
            </label>
            <input
              id="form-server-name"
              v-model="form.serverName"
              type="text"
              class="h-11 w-full rounded-lg border border-gray-300 bg-transparent px-4 py-2.5 text-sm text-gray-800 shadow-theme-xs placeholder:text-gray-400 focus:border-brand-300 focus:outline-hidden focus:ring-3 focus:ring-brand-500/10 dark:border-gray-700 dark:bg-gray-900 dark:text-white/90 dark:placeholder:text-white/30"
              placeholder="hellopro-gateway"
            />
            <p class="text-xs text-gray-400 dark:text-gray-500 mt-1">Cl&eacute; utilis&eacute;e dans le fichier .mcp.json g&eacute;n&eacute;r&eacute;</p>
          </div>

          <!-- MCP command picker (cards) -->
          <div>
            <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              Commande MCP
            </label>
            <div class="grid grid-cols-1 sm:grid-cols-2 gap-2">
              <button
                v-for="exec in executors"
                :key="exec.slug"
                type="button"
                class="group relative text-left rounded-lg border p-3 transition-colors"
                :class="form.mcp_command === exec.slug
                  ? 'border-brand-500 bg-brand-50/50 dark:bg-brand-500/10 dark:border-brand-400'
                  : 'border-gray-200 dark:border-gray-700 hover:border-gray-400 dark:hover:border-gray-500 bg-white dark:bg-gray-900'"
                @click="form.mcp_command = exec.slug"
              >
                <div class="flex items-start gap-2">
                  <div
                    v-if="exec.icon"
                    class="shrink-0 w-8 h-8 rounded-md flex items-center justify-center"
                    :class="exec.color || 'bg-gray-100 dark:bg-gray-800 text-gray-500'"
                  >
                    <i class="pi text-sm" :class="exec.icon" />
                  </div>
                  <div class="min-w-0 flex-1">
                    <div class="flex items-center gap-1.5">
                      <span class="text-sm font-semibold text-gray-900 dark:text-white truncate">{{ exec.label }}</span>
                      <span v-if="exec.sub" class="text-[11px] text-gray-500 dark:text-gray-400 truncate">{{ exec.sub }}</span>
                    </div>
                    <p
                      v-if="exec.description"
                      class="text-[11px] text-gray-600 dark:text-gray-400 mt-0.5 line-clamp-2"
                    >{{ exec.description }}</p>
                  </div>
                  <i
                    v-if="form.mcp_command === exec.slug"
                    class="pi pi-check-circle text-brand-500 text-base shrink-0"
                  />
                </div>
                <a
                  :href="`/install-guide/${exec.slug}`"
                  target="_blank"
                  rel="noopener noreferrer"
                  class="absolute bottom-2 right-2 inline-flex items-center gap-1 text-[10px] font-medium text-gray-400 hover:text-brand-500 dark:text-gray-500 dark:hover:text-brand-400 opacity-0 group-hover:opacity-100 transition-opacity"
                  :class="form.mcp_command === exec.slug ? 'opacity-100' : ''"
                  title="Voir le guide d'installation"
                  @click.stop
                >
                  Guide <i class="pi pi-external-link text-[9px]" />
                </a>
              </button>

              <!-- Custom option -->
              <button
                type="button"
                class="text-left rounded-lg border p-3 transition-colors"
                :class="form.mcp_command === 'custom'
                  ? 'border-brand-500 bg-brand-50/50 dark:bg-brand-500/10 dark:border-brand-400'
                  : 'border-dashed border-gray-300 dark:border-gray-700 hover:border-gray-400 dark:hover:border-gray-500 bg-white dark:bg-gray-900'"
                @click="form.mcp_command = 'custom'"
              >
                <div class="flex items-start gap-2">
                  <div class="shrink-0 w-8 h-8 rounded-md flex items-center justify-center bg-gray-100 dark:bg-gray-800 text-gray-500">
                    <i class="pi pi-pencil text-sm" />
                  </div>
                  <div class="min-w-0 flex-1">
                    <div class="text-sm font-semibold text-gray-900 dark:text-white">Personnalis&eacute;e</div>
                    <p class="text-[11px] text-gray-600 dark:text-gray-400 mt-0.5">Saisir une commande et des arguments libres.</p>
                  </div>
                  <i
                    v-if="form.mcp_command === 'custom'"
                    class="pi pi-check-circle text-brand-500 text-base shrink-0"
                  />
                </div>
              </button>
            </div>
          </div>

          <!-- Custom command fields -->
          <template v-if="form.mcp_command === 'custom'">
            <div>
              <label for="form-custom-command" class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Commande personnalis&eacute;e
              </label>
              <input
                id="form-custom-command"
                v-model="form.customCommand"
                type="text"
                class="h-11 w-full rounded-lg border border-gray-300 bg-transparent px-4 py-2.5 text-sm text-gray-800 shadow-theme-xs placeholder:text-gray-400 focus:border-brand-300 focus:outline-hidden focus:ring-3 focus:ring-brand-500/10 dark:border-gray-700 dark:bg-gray-900 dark:text-white/90 dark:placeholder:text-white/30"
                placeholder="my-custom-command"
              />
            </div>
            <div>
              <label for="form-custom-args" class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Pr&eacute;fixe d'arguments
              </label>
              <input
                id="form-custom-args"
                v-model="form.customArgsPrefix"
                type="text"
                class="h-11 w-full rounded-lg border border-gray-300 bg-transparent px-4 py-2.5 text-sm text-gray-800 shadow-theme-xs placeholder:text-gray-400 focus:border-brand-300 focus:outline-hidden focus:ring-3 focus:ring-brand-500/10 dark:border-gray-700 dark:bg-gray-900 dark:text-white/90 dark:placeholder:text-white/30"
                placeholder="--flag value"
              />
              <p class="text-xs text-gray-400 dark:text-gray-500 mt-1">Arguments plac&eacute;s avant l'URL du gateway</p>
            </div>
          </template>
        </div>

        <!-- Section 2: Serveurs et outils -->
        <div v-show="isEdit || currentStep === 1" :class="isEdit ? 'mt-6 pt-6 border-t border-gray-100 dark:border-gray-800' : ''">
          <h3 v-if="isEdit" class="text-sm font-semibold text-gray-900 dark:text-white mb-3">Serveurs et outils</h3>
          <DragDropPanel
            v-if="dragDropReady"
            :initial-available="dragDrop.available.value"
            :initial-selected="dragDrop.selected.value"
            @update:available="v => dragDrop.available.value = v"
            @update:selected="v => dragDrop.selected.value = v"
          />
        </div>

        <!-- Section: Instructions LLM — dedicated tab, fetches every page the
             user owns and always displays each page's server tags so the
             admin can see which backends it touches. -->
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

        <!-- Section 4: Expiration et verification -->
        <div v-show="isEdit || currentStep === expirationStepIndex" :class="isEdit ? 'mt-6 pt-6 border-t border-gray-100 dark:border-gray-800' : ''" class="space-y-4">
          <h3 v-if="isEdit" class="text-sm font-semibold text-gray-900 dark:text-white mb-3">Expiration et options</h3>
          <!-- Expiration toggle -->
          <div>
            <div class="flex items-center gap-2 mb-2">
              <input
                id="form-expires"
                v-model="expiresEnabled"
                type="checkbox"
                class="rounded border-gray-300 text-brand-500 dark:border-gray-700"
              />
              <label for="form-expires" class="text-sm font-medium text-gray-700 dark:text-gray-300">
                D&eacute;finir une date d'expiration
              </label>
            </div>
            <input
              v-if="expiresEnabled"
              v-model="form.expires_at"
              type="datetime-local"
              class="h-11 w-full rounded-lg border border-gray-300 bg-transparent px-4 py-2.5 text-sm text-gray-800 shadow-theme-xs placeholder:text-gray-400 focus:border-brand-300 focus:outline-hidden focus:ring-3 focus:ring-brand-500/10 dark:border-gray-700 dark:bg-gray-900 dark:text-white/90 dark:placeholder:text-white/30"
            />
          </div>

          <!-- Allow HTTP -->
          <div class="flex items-center gap-2">
            <input
              id="form-allow-http"
              v-model="form.allow_http"
              type="checkbox"
              class="rounded border-gray-300 text-brand-500 dark:border-gray-700"
            />
            <label for="form-allow-http" class="text-sm text-gray-700 dark:text-gray-300">
              Autoriser les connexions HTTP (non-HTTPS)
            </label>
          </div>

          <!-- Summary (create mode only) -->
          <div v-if="!isEdit" class="mt-6">
            <h3 class="text-sm font-semibold text-gray-900 dark:text-white mb-3">R&eacute;capitulatif</h3>
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
                <dt class="text-sm font-medium text-gray-500 dark:text-gray-400">Commande</dt>
                <dd class="text-sm text-gray-900 dark:text-white col-span-2 font-mono">
                  {{ form.mcp_command === 'custom' ? (form.customCommand || 'custom') : form.mcp_command }}
                </dd>
              </div>
              <div class="py-2 grid grid-cols-3 gap-4">
                <dt class="text-sm font-medium text-gray-500 dark:text-gray-400">Serveurs</dt>
                <dd class="text-sm text-gray-900 dark:text-white col-span-2">
                  {{ dragDrop.selectedCount.value.servers }} serveur(s), {{ dragDrop.selectedCount.value.tools }} outil(s)
                </dd>
              </div>
              <div class="py-2 grid grid-cols-3 gap-4">
                <dt class="text-sm font-medium text-gray-500 dark:text-gray-400">Expiration</dt>
                <dd class="text-sm text-gray-900 dark:text-white col-span-2">
                  {{ expiresEnabled && form.expires_at ? form.expires_at : 'Aucune' }}
                </dd>
              </div>
              <div class="py-2 grid grid-cols-3 gap-4">
                <dt class="text-sm font-medium text-gray-500 dark:text-gray-400">HTTP autoris&eacute;</dt>
                <dd class="text-sm text-gray-900 dark:text-white col-span-2">{{ form.allow_http ? 'Oui' : 'Non' }}</dd>
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
        <button type="button" class="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-white/5 rounded-md hover:bg-gray-200 dark:hover:bg-gray-700" @click="router.push('/tokens')">Annuler</button>
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
          <button type="button" class="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-white/5 rounded-md hover:bg-gray-200 dark:hover:bg-gray-700" @click="router.push('/tokens')">Annuler</button>
          <button v-if="currentStep < lastStepIndex" type="button" class="px-4 py-2 text-sm font-medium text-white bg-brand-500 rounded-md hover:bg-brand-600 disabled:opacity-50" :disabled="!canGoNext" @click="goNext">Suivant</button>
          <button v-if="currentStep === lastStepIndex" type="button" class="px-4 py-2 text-sm font-medium text-white bg-brand-500 rounded-md hover:bg-brand-600 disabled:opacity-50" :disabled="submitting" @click="handleSubmit">
            <i v-if="submitting" class="pi pi-spinner pi-spin mr-1" />
            Créer
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
import { useServersStore } from '@/stores/servers'
import { useToast } from '@/composables/useToast'
import { useClipboard } from '@/composables/useClipboard'
import { useDragDrop } from '@/composables/useDragDrop'
import { tokensApi } from '@/api/tokens'
import { installGuidesPublicApi } from '@/api/install-guides'
import type { InstallExecutor } from '@/types/install-guide'
import StepTabs from '@/components/shared/StepTabs.vue'
import DragDropPanel from '@/components/shared/DragDropPanel.vue'
import LeexiFilterPanel from '@/components/tokens/LeexiFilterPanel.vue'
import InstructionsPicker from '@/components/llm-instructions/InstructionsPicker.vue'
import type { ScopeToken, CreateTokenRequest } from '@/types/token'
import type { LeexiFilter } from '@/types/leexi'

const route = useRoute()
const router = useRouter()
const serversStore = useServersStore()
const toast = useToast()
const clipboard = useClipboard()
const dragDrop = useDragDrop()
const dragDropReady = ref(false)
const executors = ref<InstallExecutor[]>([])

// Step labels are dynamic: the "Acc\u00e8s Leexi" step is only shown when the
// selected servers include the Leexi backend (detected via tool_prefix === 'leexi').
const stepLabels = computed(() => {
  const labels = ['Informations de base', 'Serveurs et outils', 'Instructions LLM']
  if (hasLeexiServer.value) labels.push('Acc\u00e8s Leexi')
  labels.push('Expiration et v\u00e9rification')
  return labels
})
// Computed step indices. The Instructions LLM step is always present (index 2);
// Leexi is conditional; expiration is always last.
const instructionsStepIndex = 2
const leexiStepIndex = computed(() => (hasLeexiServer.value ? 3 : -1))
const expirationStepIndex = computed(() => (hasLeexiServer.value ? 4 : 3))
const lastStepIndex = computed(() => stepLabels.value.length - 1)
const currentStep = ref(0)
const loading = ref(false)
const submitting = ref(false)
const expiresEnabled = ref(false)
const createdToken = ref<ScopeToken | null>(null)

const isEdit = computed(() => !!route.params.id)

// hasLeexiServer is true when at least one selected server is the Leexi
// backend (identified by tool_prefix === 'leexi'). Drives whether the Leexi
// access step is shown and whether the filter is sent on submit.
const hasLeexiServer = computed(() => {
  return dragDrop.selected.value.some(s => {
    const srv = serversStore.servers.find(x => x.id === s.id)
    return srv?.tool_prefix === 'leexi'
  })
})

const form = reactive({
  name: '',
  description: '',
  serverName: 'hellopro-gateway',
  mcp_command: '',
  customCommand: '',
  customArgsPrefix: '',
  expires_at: '',
  allow_http: true,
  leexi_filter: { mode: 'none' } as LeexiFilter,
  instruction_ids: [] as string[]
})

// selectedServerIdsForPicker gives InstructionsPicker a reactive list of the
// currently chosen server IDs so it can filter + auto-prune its selection.
const selectedServerIdsForPicker = computed(() => dragDrop.getServerIds())

const completedSteps = computed(() => {
  if (!isStep1Valid.value) return []
  return Array.from({ length: lastStepIndex.value }, (_, i) => i)
})

const isStep1Valid = computed(() => {
  return !!form.name.trim()
})

const canGoNext = computed(() => {
  if (currentStep.value === 0) return isStep1Valid.value
  return currentStep.value < lastStepIndex.value
})

// If the user removes the Leexi server while sitting on the (now-gone) Leexi
// step, snap back to the new last step so the form remains navigable.
watch(hasLeexiServer, (has) => {
  if (!has && currentStep.value > lastStepIndex.value) {
    currentStep.value = lastStepIndex.value
  }
})

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

const generatedMcpJson = computed(() => {
  if (!createdToken.value) return ''
  const tokenValue = createdToken.value.token || ''
  const gatewayUrl = window.location.origin
  const serverName = form.serverName || 'hellopro-gateway'

  // Try to use mcp_config from the selected executor (from API)
  const selectedExec = executors.value.find(e => e.slug === form.mcp_command)

  // Prefer the dedicated top-level `mcp_config` field; fall back to page-builder element
  const mcpEl = Array.isArray(selectedExec?.content)
    ? selectedExec!.content.find((el: any) => el?.type === 'mcp-config')
    : null
  const mcpTemplate = (selectedExec?.mcp_config as string) || (mcpEl?.props?.code as string) || ''

  if (mcpTemplate) {
    const withAllowHttp = form.allow_http
      ? mcpTemplate.replace(/"<allow-http>"/g, '"--allow-http"')
      // Remove the entire line that contains the placeholder (with trailing comma)
      : mcpTemplate.replace(/^[ \t]*"<allow-http>"[ \t]*,?[ \t]*\r?\n/gm, '')
    return withAllowHttp
      .replace(/https?:\/\/<gateway-url>/g, gatewayUrl)
      .replace(/<gateway-url>/g, gatewayUrl.replace(/^https?:\/\//, ''))
      .replace(/<server-name>/g, serverName)
      .replace(/<token>/g, tokenValue)
      .replace(/<votre-token>/g, tokenValue)
  }

  // Fallback for custom command
  const command = form.mcp_command === 'custom'
    ? form.customCommand || 'custom-command'
    : form.mcp_command
  const headerArg = 'X-MCP-Scope-Token: ${MCP_SCOPE_TOKEN}'
  const env = { MCP_SCOPE_TOKEN: tokenValue }

  let args: string[]
  if (form.mcp_command === 'custom') {
    const prefixArgs = form.customArgsPrefix.trim()
      ? form.customArgsPrefix.trim().split(/\s+/)
      : []
    args = [...prefixArgs, gatewayUrl + '/mcp', '--header', headerArg]
  } else {
    args = [gatewayUrl + '/mcp', '--header', headerArg]
  }

  return JSON.stringify(
    { mcpServers: { [serverName]: { command, args, env } } },
    null,
    2
  )
})

onMounted(async () => {
  try {
    const [, execs] = await Promise.all([
      serversStore.fetchServers(),
      installGuidesPublicApi.listExecutors().catch(() => [] as InstallExecutor[]),
    ])
    executors.value = execs
    // Default to first executor if not already set (e.g. from edit load)
    if (execs.length && !form.mcp_command) {
      form.mcp_command = execs[0]!.slug
    }
  } catch (err) {
    console.error('[TokenFormView] Failed to fetch servers:', err)
  }

  if (isEdit.value) {
    loading.value = true
    try {
      const token = await tokensApi.get(route.params.id as string)
      form.name = token.name
      form.description = token.description || ''
      form.mcp_command = token.mcp_command || executors.value[0]?.slug || 'npx'
      if (token.server_name) {
        form.serverName = token.server_name
      }
      if (typeof token.allow_http === 'boolean') {
        form.allow_http = token.allow_http
      }
      if (token.expires_at) {
        expiresEnabled.value = true
        form.expires_at = token.expires_at.slice(0, 16)
      }
      if (token.leexi_filter) {
        form.leexi_filter = { ...token.leexi_filter }
      }
      if (token.instruction_ids) {
        form.instruction_ids = [...token.instruction_ids]
      }

      dragDrop.initWithSelection(serversStore.servers, token.server_ids, token.server_tools)
      dragDropReady.value = true
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Erreur lors du chargement du jeton')
      router.push('/tokens')
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

    const data: CreateTokenRequest = {
      name: form.name,
      description: form.description || undefined,
      server_ids: serverIds,
      server_tools: serverTools.length ? serverTools : undefined,
      instruction_ids: form.instruction_ids.length ? [...form.instruction_ids] : undefined,
      mcp_command: form.mcp_command === 'custom'
        ? form.customCommand || 'custom'
        : form.mcp_command,
      server_name: form.serverName || undefined,
      expires_at: expiresEnabled.value && form.expires_at
        ? new Date(form.expires_at).toISOString()
        : undefined,
      allow_http: form.allow_http,
      // Only send the filter when a Leexi server is actually in scope —
      // otherwise the backend would reject mode=teams/users/creator without
      // any matching backend, and 'none' is the safe default.
      leexi_filter: hasLeexiServer.value
        ? (form.leexi_filter.mode === 'none' ? { mode: 'none' } : form.leexi_filter)
        : { mode: 'none' }
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
