<template>
  <div class="p-6 max-w-3xl mx-auto">
    <!-- Page header -->
    <div class="mb-6 flex items-center gap-4">
      <button
        type="button"
        class="inline-flex items-center gap-1.5 text-sm text-gray-600 hover:text-gray-900"
        @click="router.push('/oauth2')"
      >
        <i class="pi pi-arrow-left text-xs" />
        Retour
      </button>
      <h1 class="text-2xl font-bold text-gray-900">
        {{ isEdit ? 'Modifier le client OAuth2' : 'Nouveau client OAuth2' }}
      </h1>
    </div>

    <!-- Post-creation display -->
    <template v-if="createdClient">
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

      <!-- Back button -->
      <div class="flex justify-end pt-4 border-t border-gray-100">
        <button
          class="px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-md hover:bg-blue-700"
          @click="router.push('/oauth2')"
        >
          Retour aux clients
        </button>
      </div>
    </template>

    <!-- Loading state (edit mode) -->
    <div v-else-if="loading" class="flex items-center justify-center py-20">
      <i class="pi pi-spinner pi-spin text-2xl text-gray-400" />
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
              placeholder="claude-ai-prod"
            />
          </div>

          <!-- Description -->
          <div>
            <label for="form-desc" class="block text-sm font-medium text-gray-700 mb-1">
              Description
            </label>
            <input
              id="form-desc"
              v-model="form.description"
              type="text"
              class="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:ring-blue-500 focus:border-blue-500"
              placeholder="Client pour Claude.ai production"
            />
          </div>

          <!-- Redirect URI -->
          <div>
            <label for="form-redirect-uri" class="block text-sm font-medium text-gray-700 mb-1">
              Redirect URI
            </label>
            <input
              id="form-redirect-uri"
              v-model="form.redirect_uri"
              type="url"
              class="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:ring-blue-500 focus:border-blue-500"
              placeholder="https://claude.ai/api/mcp/auth_callback"
            />
            <p class="text-xs text-gray-400 mt-1">
              URL de callback OAuth2 du client MCP (par défaut : Claude.ai)
            </p>
          </div>
        </div>

        <!-- Step 2: Serveurs et outils -->
        <div v-show="currentStep === 1">
          <label class="block text-sm font-medium text-gray-700 mb-2">
            Serveurs et outils autorisés
          </label>
          <DragDropPanel :drag-drop="dragDrop" />
        </div>

        <!-- Step 3: TTL, expiration et vérification -->
        <div v-show="currentStep === 2" class="space-y-4">
          <!-- TTL -->
          <div>
            <label for="form-ttl" class="block text-sm font-medium text-gray-700 mb-1">
              Durée de vie du token d'accès (TTL)
            </label>
            <select
              id="form-ttl"
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

          <!-- Summary -->
          <div class="border-t border-gray-100 pt-4">
            <h3 class="text-sm font-semibold text-gray-900 mb-3">Récapitulatif</h3>
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
                <dt class="text-sm font-medium text-gray-500">Redirect URI</dt>
                <dd class="text-sm text-gray-900 col-span-2 break-all">{{ form.redirect_uri }}</dd>
              </div>
              <div class="py-2 grid grid-cols-3 gap-4">
                <dt class="text-sm font-medium text-gray-500">Serveurs</dt>
                <dd class="text-sm text-gray-900 col-span-2">
                  {{ dragDrop.selectedCount.value.servers }} serveur(s), {{ dragDrop.selectedCount.value.tools }} outil(s)
                </dd>
              </div>
              <div class="py-2 grid grid-cols-3 gap-4">
                <dt class="text-sm font-medium text-gray-500">TTL token</dt>
                <dd class="text-sm text-gray-900 col-span-2">{{ ttlLabel }}</dd>
              </div>
              <div class="py-2 grid grid-cols-3 gap-4">
                <dt class="text-sm font-medium text-gray-500">Expiration</dt>
                <dd class="text-sm text-gray-900 col-span-2">
                  {{ expirationType === 'permanent' ? 'Permanent' : form.expires_at || 'Non définie' }}
                </dd>
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
          Précédent
        </button>
        <div v-else />

        <div class="flex gap-3">
          <button
            type="button"
            class="px-4 py-2 text-sm font-medium text-gray-700 bg-gray-100 rounded-md hover:bg-gray-200"
            @click="router.push('/oauth2')"
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
            {{ isEdit ? 'Enregistrer' : 'Générer les identifiants' }}
          </button>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { oauth2Api } from '@/api/oauth2'
import { useServersStore } from '@/stores/servers'
import { useToast } from '@/composables/useToast'
import { useClipboard } from '@/composables/useClipboard'
import { useDragDrop } from '@/composables/useDragDrop'
import StepTabs from '@/components/shared/StepTabs.vue'
import DragDropPanel from '@/components/shared/DragDropPanel.vue'
import type { OAuth2Client, CreateOAuth2ClientRequest } from '@/types/oauth2'

const route = useRoute()
const router = useRouter()
const serversStore = useServersStore()
const toast = useToast()
const clipboard = useClipboard()
const dragDrop = useDragDrop()

const stepLabels = ['Informations de base', 'Serveurs et outils', 'TTL, expiration et vérification']
const currentStep = ref(0)
const loading = ref(false)
const submitting = ref(false)
const expirationType = ref<'permanent' | 'custom'>('permanent')
const createdClient = ref<OAuth2Client | null>(null)

const isEdit = computed(() => !!route.params.id)

const form = reactive({
  name: '',
  description: '',
  redirect_uri: 'https://claude.ai/api/mcp/auth_callback',
  access_token_ttl: 86400,
  expires_at: ''
})

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

const isStep1Valid = computed(() => !!form.name.trim())

const completedSteps = computed(() => {
  const completed: number[] = []
  if (isStep1Valid.value) completed.push(0)
  if (isStep1Valid.value) completed.push(1)
  return completed
})

const canGoNext = computed(() => {
  if (currentStep.value === 0) return isStep1Valid.value
  if (currentStep.value === 1) return true
  return false
})

onMounted(async () => {
  if (!serversStore.servers.length) {
    await serversStore.fetchServers()
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
      dragDrop.initWithSelection(
        serversStore.servers,
        client.server_ids,
        client.server_tools
      )
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Erreur lors du chargement du client')
      router.push('/oauth2')
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
