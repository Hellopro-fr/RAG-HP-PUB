<template>
  <div>
    <PageBreadcrumb page-title="Instructions LLM" />

    <div v-if="loading" class="text-center py-12">
      <i class="pi pi-spinner pi-spin text-2xl text-brand-500" />
    </div>

    <template v-else>
      <div class="flex items-center justify-between mb-4">
        <p class="text-sm text-gray-500 dark:text-gray-400 max-w-2xl">
          Bibliothèque de pages d'instructions. Chaque page regroupe des blocs avec leur propre
          scope de serveurs ; un bloc n'est injecté dans la réponse MCP <code>initialize</code>
          que si l'un de ses serveurs est autorisé par le jeton ou le client OAuth2 actif.
        </p>
        <button
          class="px-4 py-2 text-sm font-medium text-white bg-brand-500 rounded-md hover:bg-brand-600"
          @click="router.push('/llm-instructions/new')"
        >
          Nouvelle page
        </button>
      </div>

      <div
        v-if="instructions.length"
        class="grid grid-cols-1 gap-4"
      >
        <div
          v-for="ins in instructions"
          :key="ins.id"
          class="rounded-xl border border-gray-200 bg-white dark:border-gray-700 dark:bg-gray-800 p-4 sm:p-5"
        >
          <div class="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
            <div class="min-w-0 flex-1">
              <div class="flex items-center gap-2 mb-1">
                <router-link
                  :to="`/llm-instructions/${ins.id}`"
                  class="text-sm font-semibold text-gray-900 dark:text-white truncate hover:text-brand-600 dark:hover:text-brand-400"
                >
                  {{ ins.title }}
                </router-link>
                <span class="inline-flex items-center px-1.5 py-0.5 rounded-full text-[10px] font-medium bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300">
                  {{ ins.rows.length }} bloc{{ ins.rows.length > 1 ? 's' : '' }}
                </span>
              </div>
              <p
                v-if="ins.description"
                class="text-xs text-gray-500 dark:text-gray-400 mt-1"
              >
                {{ ins.description }}
              </p>
              <p
                v-if="ins.rows.length > 0"
                class="text-xs text-gray-400 dark:text-gray-500 mt-2 line-clamp-2"
              >
                {{ firstRowPreview(ins) }}
              </p>
              <div class="flex flex-wrap gap-1 mt-3">
                <span
                  v-for="sid in distinctServerIds(ins)"
                  :key="sid"
                  class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-brand-50 text-brand-700 dark:bg-brand-500/15 dark:text-brand-200"
                >
                  {{ serverName(sid) }}
                </span>
                <span
                  v-if="distinctServerIds(ins).length === 0"
                  class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-warning-100 text-warning-700 dark:bg-warning-500/15 dark:text-warning-300"
                >
                  Aucun serveur lié
                </span>
              </div>
            </div>
            <div class="flex items-center gap-2 shrink-0">
              <button
                class="px-3 py-1.5 text-xs font-medium text-brand-600 dark:text-brand-400 border border-brand-300 dark:border-brand-500/60 rounded-md hover:bg-brand-50 dark:hover:bg-brand-500/10"
                @click="router.push(`/llm-instructions/${ins.id}`)"
              >
                Voir
              </button>
              <button
                class="px-3 py-1.5 text-xs font-medium text-gray-700 dark:text-gray-200 border border-gray-300 dark:border-gray-600 rounded-md hover:bg-gray-50 dark:hover:bg-gray-700"
                @click="router.push(`/llm-instructions/${ins.id}/edit`)"
              >
                Modifier
              </button>
              <button
                class="px-3 py-1.5 text-xs font-medium text-error-600 border border-error-300 rounded-md hover:bg-error-50 dark:hover:bg-error-500/10"
                @click="deletingId = ins.id"
              >
                Supprimer
              </button>
            </div>
          </div>
        </div>
      </div>

      <div
        v-else
        class="text-center py-12 text-gray-500 dark:text-gray-400"
      >
        <i class="pi pi-comment text-4xl mb-3 block" />
        <p class="font-medium">Aucune page pour le moment</p>
        <p class="text-sm mt-1">
          Créez une page pour guider l'agent sur quand utiliser les outils de vos serveurs.
        </p>
      </div>
    </template>

    <ConfirmDialog
      :open="!!deletingId"
      title="Supprimer la page"
      message="Cette page et tous ses blocs seront retirés des jetons et clients OAuth2 qui l'utilisent. L'action est irréversible."
      confirm-label="Supprimer"
      @update:open="deletingId = undefined"
      @confirm="confirmDelete"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { llmInstructionsApi } from '@/api/llmInstructions'
import { useServersStore } from '@/stores/servers'
import { useToast } from '@/composables/useToast'
import PageBreadcrumb from '@/components/common/PageBreadcrumb.vue'
import ConfirmDialog from '@/components/shared/ConfirmDialog.vue'
import type { LLMInstruction } from '@/types/llmInstruction'

const router = useRouter()
const serversStore = useServersStore()
const toast = useToast()

const loading = ref(true)
const instructions = ref<LLMInstruction[]>([])
const deletingId = ref<string | undefined>()

const serverNameMap = computed(() => {
  const out: Record<string, string> = {}
  for (const s of serversStore.servers) {
    out[s.id] = s.name
  }
  return out
})

function serverName(id: string): string {
  return serverNameMap.value[id] || id.slice(0, 8)
}

function distinctServerIds(ins: LLMInstruction): string[] {
  const set = new Set<string>()
  for (const row of ins.rows) {
    for (const sid of row.server_ids) set.add(sid)
  }
  return Array.from(set)
}

function firstRowPreview(ins: LLMInstruction): string {
  const row = ins.rows[0]
  if (!row) return ''
  const text = (row.body || '').replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim()
  const title = row.title ? `${row.title} — ` : ''
  return (title + text).slice(0, 160)
}

async function loadInstructions() {
  loading.value = true
  try {
    const res = await llmInstructionsApi.list()
    instructions.value = res.llm_instructions
  } catch (err) {
    toast.error('Impossible de charger les instructions.')
  } finally {
    loading.value = false
  }
}

async function confirmDelete() {
  const id = deletingId.value
  if (!id) return
  try {
    await llmInstructionsApi.remove(id)
    toast.success('Page supprimée')
    await loadInstructions()
  } catch (err) {
    toast.error('Suppression impossible')
  } finally {
    deletingId.value = undefined
  }
}

onMounted(async () => {
  await Promise.all([loadInstructions(), serversStore.fetchServers()])
})
</script>
