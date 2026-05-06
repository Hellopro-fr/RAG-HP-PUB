<template>
  <div>
    <PageBreadcrumb :page-title="loading ? 'Instruction' : (instruction?.title || 'Instruction')" />

    <!-- Loading -->
    <div v-if="loading" class="flex items-center justify-center py-20">
      <i class="pi pi-spinner pi-spin text-2xl text-gray-400 dark:text-gray-500" />
    </div>

    <template v-else-if="instruction">
      <!-- Action bar -->
      <div class="flex items-center justify-between mb-4">
        <button
          type="button"
          class="inline-flex items-center gap-1.5 text-sm text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white"
          @click="router.push('/llm-instructions')"
        >
          <i class="pi pi-arrow-left text-xs" />
          Retour à la liste
        </button>
        <div class="flex items-center gap-2">
          <button
            type="button"
            class="px-3 py-1.5 text-xs font-medium text-white bg-brand-500 rounded-md hover:bg-brand-600"
            @click="router.push(`/llm-instructions/${instruction.id}/edit`)"
          >
            Modifier
          </button>
          <button
            type="button"
            class="px-3 py-1.5 text-xs font-medium text-gray-700 dark:text-gray-200 border border-gray-300 dark:border-gray-600 rounded-md hover:bg-gray-50 dark:hover:bg-gray-700"
            @click="copyPreview"
          >
            <i class="pi pi-copy text-[11px] mr-1" />
            Copier la sortie
          </button>
        </div>
      </div>

      <!-- Page info -->
      <div class="bg-white dark:bg-gray-900 rounded-lg shadow-theme-xs border border-gray-200 dark:border-gray-800 p-5 mb-6">
        <h2 class="text-lg font-semibold text-gray-900 dark:text-white mb-2">{{ instruction.title }}</h2>
        <p v-if="instruction.description" class="text-sm text-gray-600 dark:text-gray-400 mb-3">
          {{ instruction.description }}
        </p>
        <div class="flex flex-wrap gap-3 text-xs text-gray-500 dark:text-gray-400 pt-3 border-t border-gray-100 dark:border-gray-800">
          <span>
            <i class="pi pi-list text-[10px] mr-1" />
            {{ instruction.rows.length }} bloc{{ instruction.rows.length > 1 ? 's' : '' }}
            <span v-if="generalRowCount > 0" class="text-purple-600 dark:text-purple-300">
              ({{ generalRowCount }} général{{ generalRowCount > 1 ? 'aux' : '' }})
            </span>
          </span>
          <span>
            <i class="pi pi-server text-[10px] mr-1" />
            {{ distinctServerIds.length }} serveur{{ distinctServerIds.length > 1 ? 's' : '' }} couvert{{ distinctServerIds.length > 1 ? 's' : '' }}
          </span>
          <span v-if="instruction.created_by">
            <i class="pi pi-user text-[10px] mr-1" />
            Créé par {{ instruction.created_by }}
          </span>
          <span>
            <i class="pi pi-calendar text-[10px] mr-1" />
            Mis à jour {{ formatDate(instruction.updated_at) }}
          </span>
        </div>
      </div>

      <!-- Usage -->
      <div
        v-if="usage && (usage.token_ids.length || usage.oauth2_client_ids.length)"
        class="mb-6 rounded-md border border-blue-300 bg-blue-50 dark:bg-blue-500/10 dark:border-blue-500/40 p-3 text-sm text-blue-800 dark:text-blue-200"
      >
        <i class="pi pi-info-circle mr-1" />
        Utilisée par
        <strong>{{ usage.token_ids.length }}</strong> jeton{{ usage.token_ids.length > 1 ? 's' : '' }}
        et
        <strong>{{ usage.oauth2_client_ids.length }}</strong> client{{ usage.oauth2_client_ids.length > 1 ? 's' : '' }} OAuth2.
      </div>

      <!-- Rendered blocks -->
      <h3 class="text-sm font-semibold text-gray-900 dark:text-white mb-3 uppercase tracking-wide">
        Blocs d'instruction
      </h3>
      <div v-if="instruction.rows.length === 0" class="text-center py-10 text-gray-400 dark:text-gray-500 border-2 border-dashed border-gray-300 dark:border-gray-700 rounded-lg mb-6">
        <i class="pi pi-inbox text-2xl mb-2 block" />
        <p class="text-sm">Cette page n'a aucun bloc — rien ne sera injecté.</p>
      </div>
      <div v-else class="space-y-3 mb-8">
        <article
          v-for="(row, index) in instruction.rows"
          :key="row.id || index"
          class="bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-800 overflow-hidden"
        >
          <header class="flex items-center gap-2 px-4 py-2 bg-gray-50 dark:bg-gray-800/60 border-b border-gray-100 dark:border-gray-800">
            <span class="inline-flex items-center justify-center w-6 h-6 rounded-full bg-brand-500 text-white text-xs font-semibold shrink-0">
              {{ index + 1 }}
            </span>
            <!-- Kind badge -->
            <span
              class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-semibold uppercase tracking-wide shrink-0"
              :class="row.kind === 'general'
                ? 'bg-purple-100 text-purple-700 dark:bg-purple-500/20 dark:text-purple-300'
                : 'bg-brand-50 text-brand-700 dark:bg-brand-500/15 dark:text-brand-200'"
            >
              <i :class="row.kind === 'general' ? 'pi pi-globe' : 'pi pi-server'" class="text-[9px]" />
              {{ row.kind === 'general' ? 'Général' : 'Par serveur' }}
            </span>
            <h4 class="text-sm font-semibold text-gray-900 dark:text-white truncate flex-1">
              {{ row.title?.trim() || 'Bloc sans titre' }}
            </h4>
            <div class="flex flex-wrap gap-1 justify-end">
              <template v-if="row.kind === 'general'">
                <span class="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium bg-purple-50 text-purple-700 dark:bg-purple-500/15 dark:text-purple-200">
                  Toutes les sessions
                </span>
              </template>
              <template v-else>
                <span
                  v-for="sid in row.server_ids"
                  :key="sid"
                  class="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium bg-brand-50 text-brand-700 dark:bg-brand-500/15 dark:text-brand-200"
                >
                  {{ serverName(sid) }}
                </span>
                <span
                  v-if="row.server_ids.length === 0"
                  class="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium bg-warning-100 text-warning-700 dark:bg-warning-500/15 dark:text-warning-300"
                >
                  Aucun serveur — jamais injecté
                </span>
              </template>
            </div>
          </header>
          <div class="p-4">
            <!-- Rendered HTML as the human would see it. Body comes from the
                 trusted admin WYSIWYG so we render it directly. -->
            <div class="prose prose-sm dark:prose-invert max-w-none wysiwyg-content" v-safe-html="row.body" />
          </div>
        </article>
      </div>

      <!-- Composed preview — exactly what the LLM receives on MCP initialize -->
      <h3 class="text-sm font-semibold text-gray-900 dark:text-white mb-2 uppercase tracking-wide">
        Aperçu Markdown injecté (réponse MCP <code>initialize.instructions</code>)
      </h3>
      <p class="text-xs text-gray-500 dark:text-gray-400 mb-3">
        Sortie Markdown générée côté serveur avec la <em>même</em> fonction que le gateway utilise en
        production. Le HTML des WYSIWYG est converti en Markdown GFM (gras, listes, liens, tableaux…).
        En production, un bloc <strong>par serveur</strong> n'apparaît que si son serveur est dans le scope du jeton ;
        les blocs <strong>généraux</strong> apparaissent toujours.
      </p>
      <div v-if="renderedLoading" class="text-xs text-gray-500 py-3">
        <i class="pi pi-spinner pi-spin mr-1" /> Génération de l'aperçu…
      </div>
      <pre
        v-else
        class="bg-gray-900 dark:bg-gray-950 text-gray-100 rounded-lg p-4 text-xs font-mono overflow-x-auto whitespace-pre-wrap break-words max-h-96"
        >{{ renderedMarkdown || '(vide)' }}</pre>
    </template>

    <div v-else class="text-center py-20 text-gray-500 dark:text-gray-400">
      Instruction introuvable.
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { llmInstructionsApi } from '@/api/llmInstructions'
import { useServersStore } from '@/stores/servers'
import { useToast } from '@/composables/useToast'
import { useClipboard } from '@/composables/useClipboard'
import PageBreadcrumb from '@/components/common/PageBreadcrumb.vue'
import type { LLMInstruction, LLMInstructionUsage } from '@/types/llmInstruction'

const route = useRoute()
const router = useRouter()
const serversStore = useServersStore()
const toast = useToast()
const clipboard = useClipboard()

const loading = ref(true)
const renderedLoading = ref(true)
const instruction = ref<LLMInstruction | null>(null)
const usage = ref<LLMInstructionUsage | null>(null)
const renderedMarkdown = ref('')

const serverNameMap = computed(() => {
  const out: Record<string, string> = {}
  for (const s of serversStore.servers) out[s.id] = s.name
  return out
})

function serverName(id: string): string {
  return serverNameMap.value[id] || id.slice(0, 8)
}

const distinctServerIds = computed<string[]>(() => {
  if (!instruction.value) return []
  const set = new Set<string>()
  for (const row of instruction.value.rows) {
    for (const sid of row.server_ids) set.add(sid)
  }
  return Array.from(set)
})

const generalRowCount = computed<number>(() => {
  if (!instruction.value) return 0
  return instruction.value.rows.filter((r) => r.kind === 'general').length
})

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleString('fr-FR')
  } catch {
    return iso
  }
}

async function copyPreview() {
  await clipboard.copy(renderedMarkdown.value, 'Markdown injecté')
}

onMounted(async () => {
  const id = route.params.id as string
  if (!id) {
    loading.value = false
    renderedLoading.value = false
    return
  }
  try {
    await serversStore.fetchServers()
    const [ins, u, rendered] = await Promise.all([
      llmInstructionsApi.get(id),
      llmInstructionsApi.getUsage(id),
      llmInstructionsApi.getRendered(id)
    ])
    instruction.value = ins
    usage.value = u
    renderedMarkdown.value = rendered.markdown
  } catch (err) {
    toast.error("Instruction introuvable")
    router.push('/llm-instructions')
    return
  } finally {
    loading.value = false
    renderedLoading.value = false
  }
})
</script>

<style scoped>
/* Minimal styling for the rendered HTML block. The WysiwygEditor emits
   <p>, <ul>, <a>, headings, etc. — we give them basic spacing + theme-aware
   colours without pulling in the whole Tailwind prose plugin. */
.wysiwyg-content :deep(p) {
  margin-bottom: 0.75rem;
  line-height: 1.55;
}
.wysiwyg-content :deep(p:last-child) {
  margin-bottom: 0;
}
.wysiwyg-content :deep(ul),
.wysiwyg-content :deep(ol) {
  padding-left: 1.25rem;
  margin-bottom: 0.75rem;
}
.wysiwyg-content :deep(li) {
  margin-bottom: 0.25rem;
}
.wysiwyg-content :deep(a) {
  color: rgb(59 130 246);
  text-decoration: underline;
}
.wysiwyg-content :deep(code) {
  padding: 0 0.25rem;
  border-radius: 0.25rem;
  font-size: 0.85em;
  background: rgba(148, 163, 184, 0.15);
}
.wysiwyg-content :deep(strong) {
  font-weight: 600;
}
</style>
