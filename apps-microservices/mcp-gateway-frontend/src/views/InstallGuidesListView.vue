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
    <div class="mb-10">
      <h1 class="text-2xl font-bold text-gray-900 dark:text-white">Guide d'installation</h1>
      <p class="mt-2 text-gray-600 dark:text-gray-400">
        Installez un package executor puis configurez votre client MCP pour se connecter au gateway.
      </p>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="flex items-center justify-center py-20">
      <i class="pi pi-spinner pi-spin text-2xl text-gray-400 dark:text-gray-500" />
    </div>

    <template v-else>
    <!-- ═══ 1. Configuration MCP ═══ -->
    <section class="mb-10">
      <h2 class="text-xl font-bold text-gray-900 dark:text-white mb-1">
        1. Configuration MCP
      </h2>
      <p class="text-sm text-gray-500 dark:text-gray-400 mb-5">
        Configurez votre client Claude pour se connecter au MCP Gateway.
      </p>

      <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        <router-link
          v-for="cfg in mcpConfigs"
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

    <hr class="border-gray-200 dark:border-gray-700 mb-10" />

    <!-- ═══ 2. Package executor ═══ -->
    <section class="mb-8">
      <h2 class="text-xl font-bold text-gray-900 dark:text-white mb-1">
        2. Package executor
      </h2>
      <p class="text-sm text-gray-500 dark:text-gray-400 mb-5">
        Choisissez et installez un executeur de paquets pour lancer le client MCP.
      </p>

      <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        <router-link
          v-for="cmd in commands"
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
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { installGuidesPublicApi } from '@/api/install-guides'
import type { InstallExecutor, InstallConfig } from '@/types/install-guide'

const commands = ref<InstallExecutor[]>([])
const mcpConfigs = ref<InstallConfig[]>([])
const loading = ref(true)

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
</script>
