<template>
  <div>
    <!-- Breadcrumb -->
    <nav class="mb-6 text-sm">
      <router-link to="/docs" class="text-brand-500 hover:text-brand-600 dark:text-brand-400">
        Documentation
      </router-link>
      <span class="mx-2 text-gray-400">/</span>
      <span class="text-gray-600 dark:text-gray-300">Guide d'installation</span>
    </nav>

    <!-- Header -->
    <div class="mb-6">
      <h1 class="text-2xl font-bold text-gray-900 dark:text-white">Guide d'installation</h1>
      <p class="mt-2 text-gray-600 dark:text-gray-400">
        Installez un package executor puis configurez votre client MCP pour se connecter au gateway.
      </p>
    </div>

    <CrossSectionLink
      to="/docs"
      icon="pi-book"
      message="Vous cherchez la documentation des outils MCP disponibles ?"
      link-label="Voir la documentation"
    />

    <!-- Loading skeleton -->
    <div v-if="loading" class="animate-pulse" aria-hidden="true">
      <section v-for="section in 2" :key="section" class="mb-10">
        <div class="h-6 w-48 rounded bg-gray-200 dark:bg-gray-800 mb-2" />
        <div class="h-3 w-80 max-w-full rounded bg-gray-100 dark:bg-gray-800 mb-5" />
        <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          <div
            v-for="i in 3"
            :key="i"
            class="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800/50 p-5"
          >
            <div class="flex items-center gap-3 mb-3">
              <div class="w-10 h-10 rounded-lg bg-gray-200 dark:bg-gray-800" />
              <div class="h-5 w-24 rounded bg-gray-200 dark:bg-gray-800" />
            </div>
            <div class="h-3 w-5/6 rounded bg-gray-100 dark:bg-gray-800 mb-2" />
            <div class="h-3 w-2/3 rounded bg-gray-100 dark:bg-gray-800" />
          </div>
        </div>
      </section>
    </div>

    <template v-else>
    <!-- Filters -->
    <FilterPanel
      v-if="(commands.length + mcpConfigs.length) > 4"
      :active-count="activeFilterCount"
      @reset="resetFilters"
    >
      <label class="flex flex-col gap-1 text-sm">
        <span class="text-gray-600 dark:text-gray-400">Libelle</span>
        <input
          v-model="filters.search"
          type="text"
          placeholder="Rechercher..."
          class="px-3 py-2 text-sm border border-gray-300 rounded-md bg-white dark:bg-gray-800 dark:border-gray-600 dark:text-gray-200 placeholder:text-gray-400"
        />
      </label>
    </FilterPanel>

    <!-- ═══ 1. Configuration MCP ═══ -->
    <section v-if="filteredConfigs.length" class="mb-10">
      <h2 class="text-xl font-bold text-gray-900 dark:text-white mb-1">
        1. Configuration MCP
      </h2>
      <p class="text-sm text-gray-500 dark:text-gray-400 mb-5">
        Configurez votre client Claude pour se connecter au MCP Gateway.
      </p>

      <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        <router-link
          v-for="cfg in filteredConfigs"
          :key="cfg.id"
          :to="`/install-guide/config/${cfg.slug}`"
          class="group block rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800/50 p-5 transition-all hover:border-brand-300 dark:hover:border-brand-500/50 hover:shadow-md no-underline"
        >
          <div class="flex items-center gap-3 mb-3">
            <div
              class="w-10 h-10 rounded-lg flex items-center justify-center"
              :class="cfg.color"
            >
              <i class="pi text-lg" :class="cfg.icon" />
            </div>
            <h3 class="text-base font-semibold text-gray-900 dark:text-white group-hover:text-brand-600 dark:group-hover:text-brand-400">
              {{ cfg.label }}
            </h3>
          </div>
          <p class="text-sm text-gray-600 dark:text-gray-400 leading-relaxed">
            {{ cfg.description }}
          </p>
        </router-link>
      </div>
    </section>

    <hr v-if="filteredConfigs.length && filteredCommands.length" class="border-gray-200 dark:border-gray-700 mb-10" />

    <!-- ═══ 2. Package executor ═══ -->
    <section v-if="filteredCommands.length" class="mb-8">
      <h2 class="text-xl font-bold text-gray-900 dark:text-white mb-1">
        2. Package executor
      </h2>
      <p class="text-sm text-gray-500 dark:text-gray-400 mb-5">
        Choisissez et installez un executeur de paquets pour lancer le client MCP.
      </p>

      <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        <router-link
          v-for="cmd in filteredCommands"
          :key="cmd.id"
          :to="`/install-guide/${cmd.slug}`"
          class="group block rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800/50 p-5 transition-all hover:border-brand-300 dark:hover:border-brand-500/50 hover:shadow-md no-underline"
        >
          <div class="flex items-center gap-3 mb-3">
            <div
              class="w-10 h-10 rounded-lg flex items-center justify-center"
              :class="cmd.color"
            >
              <i class="pi text-lg" :class="cmd.icon" />
            </div>
            <div>
              <h3 class="text-base font-semibold text-gray-900 dark:text-white group-hover:text-brand-600 dark:group-hover:text-brand-400">
                {{ cmd.label }}
              </h3>
              <span class="text-xs text-gray-500 dark:text-gray-400">{{ cmd.sub }}</span>
            </div>
          </div>
          <p class="text-sm text-gray-600 dark:text-gray-400 leading-relaxed">
            {{ cmd.description }}
          </p>
        </router-link>
      </div>
    </section>

    <!-- No matches -->
    <div v-if="activeFilterCount > 0 && !filteredConfigs.length && !filteredCommands.length" class="text-center py-12">
      <p class="text-gray-500 dark:text-gray-400">Aucun element ne correspond aux filtres.</p>
    </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { installGuidesPublicApi } from '@/api/install-guides'
import type { InstallExecutor, InstallConfig } from '@/types/install-guide'
import CrossSectionLink from '@/components/shared/CrossSectionLink.vue'
import FilterPanel from '@/components/shared/FilterPanel.vue'

const commands = ref<InstallExecutor[]>([])
const mcpConfigs = ref<InstallConfig[]>([])
const loading = ref(true)

const filters = reactive({
  search: '',
})

onMounted(async () => {
  try {
    const [execs, cfgs] = await Promise.all([
      installGuidesPublicApi.listExecutors(),
      installGuidesPublicApi.listConfigs(),
    ])
    commands.value = execs || []
    mcpConfigs.value = cfgs || []
  } catch {
    // Fallback: empty lists — user sees empty state
  } finally {
    loading.value = false
  }
})

const filteredConfigs = computed(() => {
  const q = filters.search.trim().toLowerCase()
  if (!q) return mcpConfigs.value
  return mcpConfigs.value.filter(c =>
    c.label.toLowerCase().includes(q) ||
    (c.description || '').toLowerCase().includes(q)
  )
})

const filteredCommands = computed(() => {
  const q = filters.search.trim().toLowerCase()
  if (!q) return commands.value
  return commands.value.filter(c =>
    c.label.toLowerCase().includes(q) ||
    (c.sub || '').toLowerCase().includes(q) ||
    (c.description || '').toLowerCase().includes(q)
  )
})

const activeFilterCount = computed(() => (filters.search.trim() ? 1 : 0))

function resetFilters() {
  filters.search = ''
}
</script>
