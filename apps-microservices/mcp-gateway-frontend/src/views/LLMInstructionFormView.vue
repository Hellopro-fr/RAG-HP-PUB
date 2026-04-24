<template>
  <div>
    <PageBreadcrumb :page-title="isEdit ? 'Modifier instruction' : 'Nouvelle instruction'" />

    <div v-if="loading" class="text-center py-12">
      <i class="pi pi-spinner pi-spin text-2xl text-brand-500" />
    </div>

    <template v-else>
      <!-- Usage warning -->
      <div
        v-if="usage && (usage.token_ids.length || usage.oauth2_client_ids.length)"
        class="mb-4 rounded-md border border-warning-300 bg-warning-50 dark:bg-warning-500/10 dark:border-warning-500/40 p-3 text-sm text-warning-800 dark:text-warning-200"
      >
        Cette page est actuellement utilisée par
        <strong>{{ usage.token_ids.length }}</strong> jeton{{ usage.token_ids.length > 1 ? 's' : '' }}
        et
        <strong>{{ usage.oauth2_client_ids.length }}</strong> client{{ usage.oauth2_client_ids.length > 1 ? 's' : '' }} OAuth2.
        Les modifications prendront effet à la prochaine connexion MCP.
      </div>

      <!-- Page-level info card -->
      <div class="bg-white dark:bg-gray-900 rounded-lg shadow-theme-xs border border-gray-200 dark:border-gray-800 p-5 mb-6">
        <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Nom de la page <span class="text-error-500">*</span>
            </label>
            <input
              v-model="form.title"
              type="text"
              maxlength="255"
              placeholder="Ex: Règles d'usage Leexi + GA"
              class="h-10 w-full rounded-lg border border-gray-300 bg-transparent px-3 py-2 text-sm text-gray-800 dark:border-gray-700 dark:bg-gray-900 dark:text-white/90"
            />
            <p class="text-xs text-gray-500 mt-1">
              Nom interne visible dans l'administration et le sélecteur des jetons.
            </p>
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Description (interne)
            </label>
            <input
              v-model="form.description"
              type="text"
              maxlength="512"
              placeholder="Note visible uniquement dans l'administration"
              class="h-10 w-full rounded-lg border border-gray-300 bg-transparent px-3 py-2 text-sm text-gray-800 dark:border-gray-700 dark:bg-gray-900 dark:text-white/90"
            />
            <p class="text-xs text-gray-500 mt-1">
              Ce texte n'est jamais envoyé à l'agent.
            </p>
          </div>
        </div>
      </div>

      <!-- Row builder — the page builder itself -->
      <div class="bg-white dark:bg-gray-900 rounded-lg shadow-theme-xs border border-gray-200 dark:border-gray-800 p-5 mb-6">
        <InstructionRowBuilder
          v-model="form.rows"
          :available-servers="serversStore.servers"
        />
        <p class="text-xs text-gray-500 dark:text-gray-400 mt-4">
          Chaque bloc est injecté uniquement pour les jetons qui ont au moins un serveur en commun avec lui.
        </p>
      </div>

      <!-- Actions -->
      <div class="flex gap-3 pt-4 border-t border-gray-200 dark:border-gray-700">
        <button
          type="button"
          :disabled="saving || !canSave"
          class="px-4 py-2 text-sm font-medium text-white bg-brand-500 rounded-md hover:bg-brand-600 disabled:opacity-50 disabled:cursor-not-allowed"
          @click="save"
        >
          <i v-if="saving" class="pi pi-spinner pi-spin mr-1" />
          {{ isEdit ? 'Enregistrer' : 'Créer' }}
        </button>
        <button
          type="button"
          class="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-200 border border-gray-300 dark:border-gray-600 rounded-md hover:bg-gray-50 dark:hover:bg-gray-700"
          @click="router.push('/llm-instructions')"
        >
          Annuler
        </button>
        <span v-if="!canSave" class="self-center text-xs text-gray-500">
          Renseignez un nom et au moins un bloc avec un corps + un serveur.
        </span>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { llmInstructionsApi } from '@/api/llmInstructions'
import { useServersStore } from '@/stores/servers'
import { useToast } from '@/composables/useToast'
import PageBreadcrumb from '@/components/common/PageBreadcrumb.vue'
import InstructionRowBuilder from '@/components/llm-instructions/InstructionRowBuilder.vue'
import type { LLMInstructionRow, LLMInstructionUsage } from '@/types/llmInstruction'

const router = useRouter()
const route = useRoute()
const serversStore = useServersStore()
const toast = useToast()

const editingId = computed(() => (route.params.id as string | undefined) || undefined)
const isEdit = computed(() => !!editingId.value)

const loading = ref(true)
const saving = ref(false)
const usage = ref<LLMInstructionUsage | null>(null)

const form = reactive({
  title: '',
  description: '',
  rows: [] as LLMInstructionRow[]
})

const canSave = computed(() => {
  if (!form.title.trim()) return false
  if (form.rows.length === 0) return false
  // Per-server blocks need at least one server; general blocks don't.
  return form.rows.every((r) => {
    if (r.body.trim().length === 0) return false
    if (r.kind === 'general') return true
    return r.server_ids.length > 0
  })
})

async function save() {
  if (!canSave.value) return
  saving.value = true
  try {
    const payload = {
      title: form.title,
      description: form.description || undefined,
      rows: form.rows.map((r) => ({
        id: r.id,
        kind: r.kind,
        title: r.title || '',
        body: r.body,
        server_ids: r.kind === 'general' ? [] : [...r.server_ids]
      }))
    }
    if (isEdit.value && editingId.value) {
      await llmInstructionsApi.update(editingId.value, payload)
      toast.success('Instruction mise à jour')
    } else {
      await llmInstructionsApi.create(payload)
      toast.success('Instruction créée')
    }
    router.push('/llm-instructions')
  } catch (err) {
    const body = (err as { body?: { error?: string } })?.body
    const msg = body?.error || (err instanceof Error ? err.message : 'Erreur inconnue')
    toast.error(`Échec de l'enregistrement: ${msg}`)
  } finally {
    saving.value = false
  }
}

onMounted(async () => {
  await serversStore.fetchServers()
  if (isEdit.value && editingId.value) {
    try {
      const ins = await llmInstructionsApi.get(editingId.value)
      form.title = ins.title
      form.description = ins.description || ''
      form.rows = (ins.rows || []).map((r) => ({
        id: r.id,
        kind: r.kind || 'per_server',
        title: r.title || '',
        body: r.body,
        server_ids: [...(r.server_ids || [])]
      }))
      usage.value = await llmInstructionsApi.getUsage(editingId.value)
    } catch (err) {
      toast.error("Impossible de charger l'instruction")
      router.push('/llm-instructions')
      return
    }
  }
  loading.value = false
})
</script>
