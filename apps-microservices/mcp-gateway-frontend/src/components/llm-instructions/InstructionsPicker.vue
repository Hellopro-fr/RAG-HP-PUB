<template>
  <div class="space-y-2">
    <div class="flex items-center justify-between">
      <label class="text-sm font-medium text-gray-700 dark:text-gray-300">
        Instructions LLM
      </label>
      <div class="flex items-center gap-3">
        <span class="text-xs text-gray-500">
          {{ selectedId ? 'Page sélectionnée' : 'Aucune sélection' }}
        </span>
        <button
          v-if="selectedId"
          type="button"
          class="text-xs text-gray-500 hover:text-gray-800 dark:hover:text-gray-200 underline"
          @click="clearSelection"
        >
          Désélectionner
        </button>
      </div>
    </div>

    <p class="text-xs text-gray-500 dark:text-gray-400">
      Sélectionnez une seule page d'instructions à injecter dans la réponse MCP <code>initialize</code>.
      Les blocs <strong>généraux</strong> apparaissent toujours ; les blocs <strong>par serveur</strong>
      n'apparaissent que si le serveur concerné est autorisé par ce jeton.
    </p>

    <!-- Warning when the single pick becomes unrenderable after a server-scope change -->
    <div
      v-if="prunedTitle"
      class="rounded-md border border-warning-300 bg-warning-50 dark:bg-warning-500/10 dark:border-warning-500/40 p-2.5 text-xs text-warning-800 dark:text-warning-200"
    >
      La page <strong>{{ prunedTitle }}</strong> a été désélectionnée car aucun de ses blocs
      ne serait injecté avec le scope actuel.
      <button
        type="button"
        class="ml-2 underline"
        @click="prunedTitle = ''"
      >
        Fermer
      </button>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="text-sm text-gray-500 py-2">
      <i class="pi pi-spinner pi-spin mr-1" /> Chargement…
    </div>

    <!-- Empty state -->
    <div
      v-else-if="available.length === 0"
      class="rounded-md border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-4 text-sm text-gray-500"
    >
      Vous n'avez pas encore créé d'instructions.
      <router-link to="/llm-instructions/new" class="text-brand-600 hover:underline ml-1">
        Créer une page →
      </router-link>
    </div>

    <!-- Picker grid — matches the MCP-command-selection card template
         (group relative rounded-lg border, selected-state highlight, check
         icon top-right) but uses a single column so every card spans the
         full width of the form. Single-select semantics still applied via
         the parent v-model holding 0-or-1 IDs. -->
    <div v-else role="radiogroup" class="grid grid-cols-1 gap-2">
      <button
        v-for="ins in sortedAvailable"
        :key="ins.id"
        type="button"
        role="radio"
        :aria-checked="isChecked(ins.id)"
        class="group relative w-full text-left rounded-lg border p-3 transition-colors"
        :class="[
          isChecked(ins.id)
            ? 'border-brand-500 bg-brand-50/50 dark:bg-brand-500/10 dark:border-brand-400'
            : willRender(ins)
              ? 'border-gray-200 dark:border-gray-700 hover:border-gray-400 dark:hover:border-gray-500 bg-white dark:bg-gray-900'
              : 'border-dashed border-gray-300 dark:border-gray-700 hover:border-gray-400 dark:hover:border-gray-500 bg-gray-50 dark:bg-gray-900/60'
        ]"
        @click="toggleSelection(ins.id)"
      >
        <div class="flex items-start gap-2">
          <!-- Left icon — matches the Commande MCP pattern. Globe when the
               page contains general blocks, server icon otherwise. -->
          <div
            class="shrink-0 w-8 h-8 rounded-md flex items-center justify-center"
            :class="hasGeneralRow(ins)
              ? 'bg-purple-100 text-purple-600 dark:bg-purple-500/20 dark:text-purple-300'
              : 'bg-brand-50 text-brand-600 dark:bg-brand-500/15 dark:text-brand-300'"
          >
            <i
              :class="hasGeneralRow(ins) ? 'pi pi-globe' : 'pi pi-comment'"
              class="text-sm"
            />
          </div>

          <div class="min-w-0 flex-1">
            <div class="flex items-center gap-1.5 flex-wrap">
              <span class="text-sm font-semibold text-gray-900 dark:text-white truncate">
                {{ ins.title }}
              </span>
              <span class="text-[11px] text-gray-500 dark:text-gray-400 truncate">
                {{ ins.rows.length }} bloc{{ ins.rows.length > 1 ? 's' : '' }}
              </span>
              <span
                v-if="!willRender(ins)"
                class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full text-[10px] font-medium bg-warning-100 text-warning-700 dark:bg-warning-500/15 dark:text-warning-300"
                title="Aucun bloc ne sera injecté avec le scope actuel de ce jeton"
              >
                <i class="pi pi-exclamation-triangle text-[9px]" />
                Hors scope
              </span>
            </div>
            <p
              v-if="ins.description"
              class="text-[11px] text-gray-600 dark:text-gray-400 mt-0.5 line-clamp-2"
            >
              {{ ins.description }}
            </p>

            <!-- Server tags + "Général" badge: the always-visible summary
                 of which backends this page concerns. -->
            <div class="flex flex-wrap items-center gap-1 mt-2">
              <span
                v-if="hasGeneralRow(ins)"
                class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium bg-purple-100 text-purple-700 dark:bg-purple-500/20 dark:text-purple-300"
              >
                <i class="pi pi-globe text-[9px]" />
                Général
              </span>
              <span
                v-for="sid in distinctServerIds(ins)"
                :key="sid"
                class="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium"
                :class="serverIds.includes(sid)
                  ? 'bg-brand-50 text-brand-700 dark:bg-brand-500/15 dark:text-brand-200'
                  : 'bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-400'"
                :title="serverIds.includes(sid) ? 'Serveur dans le scope' : 'Serveur hors du scope actuel'"
              >
                <i class="pi pi-server text-[9px] mr-0.5" />
                {{ serverName(sid) }}
              </span>
            </div>
          </div>

          <!-- Top-right check icon, identical treatment to the Commande MCP cards. -->
          <i
            v-if="isChecked(ins.id)"
            class="pi pi-check-circle text-brand-500 text-base shrink-0"
          />
        </div>

        <!-- Detail link — opens in a new tab so the user can inspect the
             composed Markdown without losing the token / OAuth2 form state.
             Plain <a> (instead of <router-link>) so target="_blank" is
             honoured consistently; rel="noopener noreferrer" for security. -->
        <a
          :href="`/llm-instructions/${ins.id}`"
          target="_blank"
          rel="noopener noreferrer"
          class="absolute bottom-2 right-2 inline-flex items-center gap-1 text-[10px] font-medium text-gray-400 hover:text-brand-500 dark:text-gray-500 dark:hover:text-brand-400 opacity-0 group-hover:opacity-100 transition-opacity"
          :class="isChecked(ins.id) ? 'opacity-100' : ''"
          title="Voir le détail de la page (nouvel onglet)"
          @click.stop
        >
          Détail <i class="pi pi-external-link text-[9px]" />
        </a>
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { llmInstructionsApi } from '@/api/llmInstructions'
import { useServersStore } from '@/stores/servers'
import type { LLMInstruction } from '@/types/llmInstruction'

// The v-model stays `string[]` for backend-payload symmetry (the token /
// OAuth2 DTOs accept `instruction_ids[]`), but at the UI level we enforce a
// single selection — the array holds either 0 or 1 entries.
const props = defineProps<{
  modelValue: string[]
  serverIds: string[] // currently selected server IDs on the parent form
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: string[]): void
}>()

const serversStore = useServersStore()

const loading = ref(false)
const available = ref<LLMInstruction[]>([])
const prunedTitle = ref('') // non-empty = surface a warning about the last pruned pick

// selectedId is the single-pick convenience view over the v-model array. Empty
// string means "no selection" — what `modelValue = []` represents.
const selectedId = computed<string>(() => props.modelValue[0] ?? '')

const serverNameMap = computed(() => {
  const out: Record<string, string> = {}
  for (const s of serversStore.servers) out[s.id] = s.name
  return out
})

function serverName(id: string): string {
  return serverNameMap.value[id] || id.slice(0, 6)
}

function isChecked(id: string): boolean {
  return selectedId.value === id
}

// toggleSelection implements the single-select toggle: clicking the currently
// selected card clears the pick; clicking any other card replaces the pick.
// This mirrors the toggle-radio UX and drives the v-model directly.
function toggleSelection(id: string) {
  if (selectedId.value === id) {
    emit('update:modelValue', [])
  } else {
    emit('update:modelValue', [id])
  }
}

function clearSelection() {
  emit('update:modelValue', [])
}

// hasGeneralRow tells whether any block in the page applies universally. Used
// for the "Général" pill and for the renderability calculation (general rows
// always render, so the page is renderable even if no server overlaps).
function hasGeneralRow(ins: LLMInstruction): boolean {
  return ins.rows.some((r) => r.kind === 'general')
}

// distinctServerIds unions the per-row server scopes so the chip row reflects
// every backend the page touches — the "tags of the server that concerned the
// instruction" the user asked for.
function distinctServerIds(ins: LLMInstruction): string[] {
  const set = new Set<string>()
  for (const row of ins.rows) {
    for (const sid of row.server_ids) set.add(sid)
  }
  return Array.from(set)
}

// willRender mirrors the backend composer/validator: a page is renderable for
// the current server scope if it has any general row OR any per-server row
// whose server_ids intersect the currently selected set.
function willRender(ins: LLMInstruction): boolean {
  if (hasGeneralRow(ins)) return true
  const allowed = new Set(props.serverIds)
  return ins.rows.some(
    (r) => r.kind === 'per_server' && r.server_ids.some((sid) => allowed.has(sid))
  )
}

// sortedAvailable puts renderable pages first so the most relevant choices
// sit at the top; out-of-scope pages stay visible but demoted so admins can
// still see what exists (they might plan to add servers later).
const sortedAvailable = computed<LLMInstruction[]>(() => {
  const list = [...available.value]
  list.sort((a, b) => {
    const ar = willRender(a) ? 0 : 1
    const br = willRender(b) ? 0 : 1
    if (ar !== br) return ar - br
    return a.title.localeCompare(b.title, 'fr')
  })
  return list
})

async function fetchAvailable() {
  loading.value = true
  try {
    // Fetch ALL of the current user's pages (no server filter) so the panel
    // can always surface every page the user owns along with its server tags.
    const res = await llmInstructionsApi.list()
    available.value = res.llm_instructions
  } catch (err) {
    console.error('[InstructionsPicker] list failed', err)
    available.value = []
  } finally {
    loading.value = false
  }
}

// Auto-prune: when the server scope changes, drop the pick if its page has
// no block that would render under the new scope. Pages with any general row
// are immune. The pruned title surfaces in a dismissible warning.
watch(
  () => props.serverIds,
  () => {
    if (!selectedId.value) return
    const ins = available.value.find((i) => i.id === selectedId.value)
    if (!ins) return // unknown (not loaded yet) — be conservative, keep it
    if (!willRender(ins)) {
      prunedTitle.value = ins.title
      emit('update:modelValue', [])
    }
  }
)

onMounted(() => {
  fetchAvailable()
})
</script>
