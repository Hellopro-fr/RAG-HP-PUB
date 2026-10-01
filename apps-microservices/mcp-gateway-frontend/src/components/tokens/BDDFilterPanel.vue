<template>
  <div v-if="hasBddServer" class="space-y-3">
    <!-- Loading -->
    <div v-if="loading" class="flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400">
      <i class="pi pi-spinner pi-spin" /> Chargement des tables BDD&hellip;
    </div>

    <!-- Service unavailable (503) -->
    <div
      v-else-if="serviceUnavailable"
      class="rounded-md border border-warning-300 dark:border-warning-500/30 bg-warning-50 dark:bg-warning-500/15 p-3 text-sm text-warning-800 dark:text-warning-400"
    >
      <i class="pi pi-exclamation-triangle mr-1" />
      L'int&eacute;gration BDD n'est pas configur&eacute;e.
    </div>

    <!-- Generic load error -->
    <div
      v-else-if="loadError"
      class="rounded-md border border-warning-300 dark:border-warning-500/30 bg-warning-50 dark:bg-warning-500/15 p-3 text-sm text-warning-800 dark:text-warning-400"
    >
      <i class="pi pi-exclamation-triangle mr-1" />
      {{ loadError }}
    </div>

    <!-- Empty registry -->
    <div
      v-else-if="allTables.length === 0"
      class="rounded-md border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900/40 p-3 text-sm text-gray-600 dark:text-gray-400"
    >
      <i class="pi pi-info-circle mr-1" />
      Aucune table BDD enregistr&eacute;e.
      <router-link
        to="/bdd-tables"
        class="ml-1 text-brand-500 hover:text-brand-600 dark:text-brand-400 dark:hover:text-brand-300 underline"
      >
        Configurer la liste des tables BDD
      </router-link>
    </div>

    <!-- Database groups -->
    <template v-else>
      <div
        v-for="group in groups"
        :key="group.id"
        class="rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900"
      >
        <!-- Group header (collapsible) -->
        <button
          type="button"
          class="w-full flex items-center justify-between px-3 py-2 text-left hover:bg-gray-50 dark:hover:bg-gray-800/40 rounded-t-lg"
          @click="toggleGroup(group.id)"
        >
          <span class="flex items-center gap-2 text-sm font-medium text-gray-800 dark:text-gray-200">
            <i
              class="pi text-xs text-gray-400"
              :class="expanded[group.id] ? 'pi-chevron-down' : 'pi-chevron-right'"
            />
            {{ group.name }}
            <span class="text-xs text-gray-400 dark:text-gray-500">
              ({{ groupSelectedCount(group.id) }}/{{ group.tables.length }})
            </span>
          </span>
          <span
            v-if="group.tables.length > 0"
            class="text-xs text-brand-500 hover:text-brand-600 dark:text-brand-400"
            @click.stop="toggleGroupAll(group.id)"
          >
            {{ groupAllSelected(group.id) ? 'Tout désélectionner' : 'Tout sélectionner' }}
          </span>
        </button>

        <!-- Group body -->
        <div
          v-if="expanded[group.id]"
          class="border-t border-gray-100 dark:border-gray-800 divide-y divide-gray-100 dark:divide-gray-800 max-h-56 overflow-y-auto"
        >
          <label
            v-for="t in group.tables"
            :key="t.id"
            class="flex items-start gap-2 px-3 py-2 text-sm text-gray-700 dark:text-gray-300 cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800/50"
          >
            <input
              type="checkbox"
              class="mt-0.5 rounded border-gray-300 text-brand-500 dark:border-gray-700"
              :checked="selectedSet.has(t.id)"
              :disabled="disabled"
              @change="toggleTable(t.id, ($event.target as HTMLInputElement).checked)"
            />
            <span class="flex-1 min-w-0">
              <span class="font-mono text-[13px]">{{ t.table_name }}</span>
              <span
                v-if="t.description"
                class="block text-xs text-gray-400 dark:text-gray-500 truncate"
                :title="t.description"
              >
                {{ t.description }}
              </span>
            </span>
          </label>
          <div
            v-if="group.tables.length === 0"
            class="px-3 py-2 text-sm text-gray-400 dark:text-gray-500"
          >
            Aucune table enregistr&eacute;e pour cette base.
          </div>
        </div>
      </div>

      <p class="text-xs text-gray-400 dark:text-gray-500 mt-1">
        Aucune table coch&eacute;e = acc&egrave;s complet &agrave; toutes les tables BDD.
      </p>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, reactive, onMounted, watch } from 'vue'
import { bddApi } from '@/api/bdd'
import { HELLOPRO_DATABASES } from '@/types/bdd'
import type { BDDFilter, BDDUsedTable } from '@/types/bdd'
import type { Server } from '@/types/server'
import { ApiError } from '@/types/api'

const props = defineProps<{
  modelValue: BDDFilter
  serverIds: string[]
  servers: Server[]
  disabled?: boolean
}>()

const emit = defineEmits<{ (e: 'update:modelValue', value: BDDFilter): void }>()

const allTables = ref<BDDUsedTable[]>([])
const loading = ref(false)
const loadError = ref<string | null>(null)
const serviceUnavailable = ref(false)
let loaded = false

// Per-database expanded/collapsed state. All groups start expanded.
const expanded = reactive<Record<number, boolean>>(
  HELLOPRO_DATABASES.reduce((acc, db) => {
    acc[db.id] = true
    return acc
  }, {} as Record<number, boolean>),
)

// hasBddServer: true when at least one currently-picked server has
// tool_prefix === 'bdd'. Drives whether the panel renders at all.
const hasBddServer = computed(() =>
  props.serverIds.some((id) => {
    const srv = props.servers.find((s) => s.id === id)
    return srv?.tool_prefix === 'bdd'
  }),
)

const selectedSet = computed(() => new Set(props.modelValue.used_table_ids || []))

// Group tables by database id, preserving HELLOPRO_DATABASES ordering.
const groups = computed(() =>
  HELLOPRO_DATABASES.map((db) => ({
    id: db.id,
    name: db.name,
    tables: allTables.value
      .filter((t) => t.database_id === db.id)
      .sort((a, b) => a.table_name.localeCompare(b.table_name)),
  })),
)

function groupSelectedCount(dbId: number): number {
  const ids = groups.value.find((g) => g.id === dbId)?.tables.map((t) => t.id) || []
  return ids.filter((id) => selectedSet.value.has(id)).length
}

function groupAllSelected(dbId: number): boolean {
  const ids = groups.value.find((g) => g.id === dbId)?.tables.map((t) => t.id) || []
  return ids.length > 0 && ids.every((id) => selectedSet.value.has(id))
}

function toggleGroup(dbId: number) {
  expanded[dbId] = !expanded[dbId]
}

function toggleGroupAll(dbId: number) {
  if (props.disabled) return
  const ids = groups.value.find((g) => g.id === dbId)?.tables.map((t) => t.id) || []
  if (ids.length === 0) return
  const next = new Set(props.modelValue.used_table_ids || [])
  if (groupAllSelected(dbId)) {
    ids.forEach((id) => next.delete(id))
  } else {
    ids.forEach((id) => next.add(id))
  }
  emit('update:modelValue', { used_table_ids: Array.from(next) })
}

function toggleTable(id: string, checked: boolean) {
  if (props.disabled) return
  const next = new Set(props.modelValue.used_table_ids || [])
  if (checked) next.add(id)
  else next.delete(id)
  emit('update:modelValue', { used_table_ids: Array.from(next) })
}

async function ensureLoaded() {
  if (loaded || loading.value) return
  loading.value = true
  loadError.value = null
  serviceUnavailable.value = false
  try {
    // Single call covers all 3 databases — server-side aggregates.
    const res = await bddApi.listUsed()
    allTables.value = res.tables || []
    loaded = true
  } catch (err) {
    if (err instanceof ApiError && err.status === 503) {
      serviceUnavailable.value = true
    } else {
      const message = err instanceof Error ? err.message : String(err)
      loadError.value = `Impossible de charger les tables BDD : ${message}`
    }
  } finally {
    loading.value = false
  }
}

// Lazy-load on mount only when the panel is actually visible. Also re-check
// when the user adds a BDD server later in the form.
watch(
  hasBddServer,
  (has) => {
    if (has) ensureLoaded()
  },
  { immediate: true },
)

onMounted(() => {
  if (hasBddServer.value) ensureLoaded()
})
</script>
