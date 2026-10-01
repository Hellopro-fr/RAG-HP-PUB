<template>
  <div>
    <div class="flex items-center justify-between mb-3">
      <div class="flex items-center gap-2">
        <h3 class="text-sm font-semibold text-gray-900 dark:text-white">
          Blocs d'instructions
        </h3>
        <span class="text-xs text-gray-500">
          ({{ rows.length }} bloc{{ rows.length > 1 ? 's' : '' }})
        </span>
      </div>
      <div class="flex items-center gap-2">
        <button
          type="button"
          class="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-gray-700 dark:text-gray-200 border border-gray-300 dark:border-gray-600 rounded-md hover:bg-gray-50 dark:hover:bg-gray-700"
          @click="addRow('general')"
        >
          <i class="pi pi-globe text-[10px]" />
          Bloc général
        </button>
        <button
          type="button"
          class="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-white bg-brand-500 rounded-md hover:bg-brand-600"
          @click="addRow('per_server')"
        >
          <i class="pi pi-plus text-[10px]" />
          Bloc par serveur
        </button>
      </div>
    </div>

    <div v-if="availableServers.length === 0" class="rounded-md border border-dashed border-gray-300 dark:border-gray-600 bg-gray-50 dark:bg-gray-800/30 p-4 text-sm text-gray-500 mb-3">
      Aucun serveur MCP n'est disponible. Vous pouvez tout de même créer des blocs <strong>généraux</strong> qui s'appliquent à toutes les sessions.
    </div>

    <div v-if="rows.length === 0" class="text-center py-10 text-gray-400 dark:text-gray-500 border-2 border-dashed border-gray-300 dark:border-gray-700 rounded-lg">
      <i class="pi pi-inbox text-2xl mb-2 block" />
      <p class="text-sm">Aucun bloc. Choisissez un type ci-dessus pour commencer.</p>
    </div>

    <VueDraggable
      v-else
      v-model="rows"
      :animation="180"
      handle=".row-drag-handle"
      ghost-class="row-ghost"
      class="space-y-3"
    >
      <div
        v-for="(row, index) in rows"
        :key="row._uid"
        class="rounded-lg border bg-white dark:bg-gray-900 transition-colors"
        :class="[
          expandedIndex === index ? 'ring-1 ring-brand-500/30' : '',
          row.kind === 'general'
            ? 'border-purple-300 dark:border-purple-500/60'
            : 'border-gray-200 dark:border-gray-700'
        ]"
      >
        <!-- Row header -->
        <div
          class="flex items-center gap-2 px-3 py-2 border-b cursor-pointer"
          :class="expandedIndex === index
            ? 'border-gray-100 dark:border-gray-800 bg-brand-50/40 dark:bg-brand-500/5'
            : 'border-transparent hover:bg-gray-50 dark:hover:bg-gray-800/50'"
          @click="toggleExpand(index)"
        >
          <!-- Drag handle -->
          <span
            class="row-drag-handle cursor-grab active:cursor-grabbing p-1 text-gray-400 hover:text-gray-600"
            title="Glisser pour réorganiser"
            @click.stop
          >
            <i class="pi pi-bars text-xs" />
          </span>

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

          <div class="min-w-0 flex-1">
            <p class="text-sm font-medium text-gray-800 dark:text-gray-200 truncate">
              {{ row.title?.trim() || previewText(row.body) || 'Bloc sans titre' }}
            </p>
            <p class="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
              <template v-if="row.kind === 'general'">
                Injecté sur toutes les sessions
              </template>
              <template v-else>
                {{ row.server_ids.length }} serveur{{ row.server_ids.length > 1 ? 's' : '' }}
                <span v-if="row.server_ids.length">
                  · {{ serverSummary(row.server_ids) }}
                </span>
              </template>
            </p>
          </div>

          <div class="flex items-center gap-0.5 shrink-0">
            <button
              type="button"
              class="p-1.5 rounded text-gray-400 hover:text-error-500 hover:bg-error-50 dark:hover:bg-error-500/10"
              title="Supprimer"
              @click.stop="removeRow(index)"
            >
              <i class="pi pi-times text-xs" />
            </button>
            <i
              class="pi ml-1 text-xs text-gray-400 transition-transform"
              :class="expandedIndex === index ? 'pi-chevron-up' : 'pi-chevron-down'"
            />
          </div>
        </div>

        <!-- Expanded body -->
        <div v-if="expandedIndex === index" class="p-4 space-y-4" @click.stop>
          <!-- Kind toggle -->
          <div>
            <label class="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">
              Type de bloc
            </label>
            <div class="inline-flex rounded-md border border-gray-300 dark:border-gray-600 overflow-hidden">
              <button
                type="button"
                class="px-3 py-1.5 text-xs font-medium transition-colors"
                :class="row.kind === 'per_server'
                  ? 'bg-brand-500 text-white'
                  : 'bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700'"
                @click="changeKind(row, 'per_server')"
              >
                <i class="pi pi-server text-[10px] mr-1" />
                Par serveur
              </button>
              <button
                type="button"
                class="px-3 py-1.5 text-xs font-medium border-l border-gray-300 dark:border-gray-600 transition-colors"
                :class="row.kind === 'general'
                  ? 'bg-purple-500 text-white'
                  : 'bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700'"
                @click="changeKind(row, 'general')"
              >
                <i class="pi pi-globe text-[10px] mr-1" />
                Général
              </button>
            </div>
            <p class="text-[11px] text-gray-500 dark:text-gray-400 mt-1">
              <template v-if="row.kind === 'general'">
                Ce bloc est injecté sur chaque session MCP, quels que soient les serveurs autorisés par le jeton.
              </template>
              <template v-else>
                Ce bloc n'est injecté que si au moins un des serveurs sélectionnés est dans le scope du jeton.
              </template>
            </p>
          </div>

          <div>
            <label class="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">
              Titre du bloc (optionnel)
            </label>
            <input
              v-model="row.title"
              type="text"
              maxlength="255"
              placeholder="Ex: Préférer la recherche"
              class="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200"
            />
            <p class="text-[11px] text-gray-400 mt-1">
              Rendu comme <code>## {{ row.title?.trim() || 'Titre' }}</code> en tête du bloc injecté.
            </p>
          </div>

          <div>
            <label class="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">
              Contenu (HTML) <span class="text-error-500">*</span>
            </label>
            <WysiwygEditor
              v-model="row.body"
              placeholder="Décrivez quand et comment l'agent doit utiliser les outils concernés..."
            />
            <p class="text-[11px] text-gray-400 mt-1">
              Le HTML est transmis tel quel à l'agent via la réponse MCP <code>initialize</code>.
            </p>
          </div>

          <!-- Server selector only for per_server blocks -->
          <div v-if="row.kind === 'per_server'">
            <label class="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-2">
              Serveurs concernés par ce bloc <span class="text-error-500">*</span>
            </label>
            <div class="flex flex-wrap gap-2">
              <label
                v-for="srv in availableServers"
                :key="srv.id"
                class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md border cursor-pointer text-xs transition-colors select-none"
                :class="row.server_ids.includes(srv.id)
                  ? 'border-brand-500 bg-brand-50 text-brand-700 dark:bg-brand-500/15 dark:text-brand-200'
                  : 'border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 hover:border-gray-400'"
              >
                <input
                  type="checkbox"
                  :checked="row.server_ids.includes(srv.id)"
                  class="sr-only"
                  @change="toggleServer(row, srv.id, ($event.target as HTMLInputElement).checked)"
                />
                <i
                  :class="row.server_ids.includes(srv.id) ? 'pi pi-check-circle' : 'pi pi-circle'"
                  class="text-[10px]"
                />
                {{ srv.name }}
                <span v-if="srv.tool_prefix" class="text-[10px] text-gray-400">
                  ({{ srv.tool_prefix }}_*)
                </span>
              </label>
            </div>
            <p v-if="row.server_ids.length === 0" class="text-[11px] text-warning-600 dark:text-warning-400 mt-2">
              Au moins un serveur doit être sélectionné. Le bloc ne sera sinon jamais injecté.
            </p>
          </div>

          <!-- Visual cue that general blocks ignore server scope -->
          <div
            v-else
            class="flex items-center gap-2 rounded-md border border-purple-200 dark:border-purple-500/40 bg-purple-50 dark:bg-purple-500/10 px-3 py-2 text-xs text-purple-800 dark:text-purple-200"
          >
            <i class="pi pi-globe text-xs" />
            Bloc général — aucun serveur à sélectionner, il s'applique à toutes les sessions.
          </div>
        </div>
      </div>
    </VueDraggable>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { VueDraggable } from 'vue-draggable-plus'
import WysiwygEditor from '@/components/shared/WysiwygEditor.vue'
import type { LLMInstructionRow, LLMInstructionRowKind } from '@/types/llmInstruction'
import type { Server } from '@/types/server'

// InternalRow adds a stable client-side key so v-for and drag reorder don't
// scramble when rows are moved (DB IDs may be undefined for new rows).
interface InternalRow extends LLMInstructionRow {
  _uid: string
}

const props = defineProps<{
  modelValue: LLMInstructionRow[]
  availableServers: Server[]
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: LLMInstructionRow[]): void
}>()

const expandedIndex = ref<number | null>(0)

const rows = computed<InternalRow[]>({
  get: () =>
    props.modelValue.map((r, i) => ({
      ...r,
      kind: (r.kind || 'per_server') as LLMInstructionRowKind,
      _uid: (r as InternalRow)._uid || `row-${i}-${Date.now()}`
    })),
  set: (val) => {
    // Strip the client-side _uid before persisting upstream.
    emit(
      'update:modelValue',
      val.map(({ _uid: _, ...rest }) => rest as LLMInstructionRow)
    )
  }
})

function uid(): string {
  return 'row-' + Date.now().toString(36) + Math.random().toString(36).slice(2, 7)
}

function previewText(html: string): string {
  if (!html) return ''
  return html.replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim().slice(0, 70)
}

function serverSummary(serverIds: string[]): string {
  const names = serverIds
    .slice(0, 3)
    .map((id) => props.availableServers.find((s) => s.id === id)?.name || id.slice(0, 6))
  if (serverIds.length > 3) names.push(`+${serverIds.length - 3}`)
  return names.join(', ')
}

function toggleExpand(index: number) {
  expandedIndex.value = expandedIndex.value === index ? null : index
}

function addRow(kind: LLMInstructionRowKind) {
  const next: InternalRow[] = [
    ...rows.value,
    { _uid: uid(), kind, title: '', body: '', server_ids: [] }
  ]
  rows.value = next
  expandedIndex.value = next.length - 1
}

function removeRow(index: number) {
  const next = [...rows.value]
  next.splice(index, 1)
  rows.value = next
  if (expandedIndex.value === index) {
    expandedIndex.value = null
  } else if (expandedIndex.value !== null && expandedIndex.value > index) {
    expandedIndex.value--
  }
}

// changeKind flips the row type. When switching to "general", server_ids are
// wiped (the backend will drop them anyway, but clearing here keeps the UI
// honest and the network payload clean).
function changeKind(row: InternalRow, kind: LLMInstructionRowKind) {
  if (row.kind === kind) return
  const next = rows.value.map((r) =>
    r._uid === row._uid
      ? { ...r, kind, server_ids: kind === 'general' ? [] : r.server_ids }
      : r
  )
  rows.value = next
}

function toggleServer(row: InternalRow, serverId: string, checked: boolean) {
  const set = new Set(row.server_ids)
  if (checked) set.add(serverId)
  else set.delete(serverId)
  const next = rows.value.map((r) =>
    r._uid === row._uid ? { ...r, server_ids: Array.from(set) } : r
  )
  rows.value = next
}
</script>

<style scoped>
/* Soft feedback for the drop placeholder while dragging. */
.row-ghost {
  opacity: 0.35;
  background: rgb(219 234 254);
}
</style>
