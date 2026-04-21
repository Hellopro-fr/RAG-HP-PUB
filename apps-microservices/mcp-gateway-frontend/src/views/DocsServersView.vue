<template>
  <div>
    <div class="mb-6">
      <h1 class="text-2xl font-bold text-gray-900 dark:text-white">Serveurs MCP disponibles</h1>
      <p class="mt-1 text-sm text-gray-600 dark:text-gray-400">
        Documentation des outils disponibles via le MCP Gateway.
      </p>
    </div>

    <CrossSectionLink
      to="/install-guide"
      icon="pi-download"
      message="Pret a connecter votre client MCP au gateway ?"
      link-label="Suivre le guide d'installation"
    />

    <!-- Loading skeleton -->
    <div
      v-if="loading"
      class="grid grid-cols-1 md:grid-cols-2 gap-4 animate-pulse"
      aria-hidden="true"
    >
      <div
        v-for="i in 4"
        :key="i"
        class="p-5 rounded-lg border border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-900"
      >
        <div class="flex items-center gap-3 mb-3">
          <div class="w-8 h-8 rounded bg-gray-200 dark:bg-gray-800" />
          <div class="h-5 w-1/3 rounded bg-gray-200 dark:bg-gray-800" />
        </div>
        <div class="h-3 w-5/6 rounded bg-gray-100 dark:bg-gray-800 mb-2" />
        <div class="h-3 w-2/3 rounded bg-gray-100 dark:bg-gray-800 mb-4" />
        <div class="h-3 w-20 rounded bg-gray-100 dark:bg-gray-800" />
      </div>
    </div>

    <template v-else>
      <!-- Search -->
      <div v-if="servers.length > 4" class="mb-6">
        <input
          v-model="search"
          type="text"
          placeholder="Rechercher un serveur..."
          class="w-full max-w-md px-3 py-2 text-sm border border-gray-300 rounded-md bg-white dark:bg-gray-800 dark:border-gray-600 dark:text-gray-200 placeholder:text-gray-400"
        />
      </div>

      <!-- Server grid -->
      <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
        <router-link
          v-for="server in filteredServers"
          :key="server.slug"
          :to="`/docs/${server.slug}`"
          class="block p-5 rounded-lg border border-gray-200 bg-white hover:border-brand-300 hover:shadow-sm transition dark:border-gray-800 dark:bg-gray-900 dark:hover:border-brand-600 no-underline"
        >
          <div class="mb-2">
            <div class="flex items-center gap-3">
              <img
                v-if="server.icon"
                :src="server.icon"
                :alt="server.name"
                class="w-8 h-8 flex-shrink-0 rounded"
              />
              <h3 class="text-base font-semibold text-gray-900 dark:text-white">
                {{ server.name }}
              </h3>
            </div>
            <p v-if="server.description" class="text-sm text-gray-500 dark:text-gray-400 mt-1 line-clamp-2">
              {{ stripHtml(server.description) }}
            </p>
          </div>
          <div class="flex items-center gap-3 text-xs text-gray-500 dark:text-gray-400">
            <span class="flex items-center gap-1">
              <svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                <path stroke-linecap="round" stroke-linejoin="round" d="M11.42 15.17l-5.384-3.19A.5.5 0 015.5 11.5V4.257a.5.5 0 01.57-.495l5.383.685a.5.5 0 01.428.49v9.735a.5.5 0 01-.461.498zM18.5 4.257v7.243a.5.5 0 01-.536.48l-5.383-.685" />
              </svg>
              {{ server.tools_count }} outil{{ server.tools_count !== 1 ? 's' : '' }}
            </span>
          </div>
        </router-link>
      </div>

      <!-- Empty search -->
      <div v-if="filteredServers.length === 0 && search" class="text-center py-12">
        <p class="text-gray-500 dark:text-gray-400">
          Aucun serveur ne correspond a "{{ search }}".
        </p>
      </div>

      <!-- No docs at all -->
      <div v-if="servers.length === 0 && !search" class="text-center py-12">
        <p class="text-gray-500 dark:text-gray-400">
          Aucune documentation disponible.
        </p>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { docsApi } from '@/api/docs';
import type { DocsServerSummary } from '@/types/docs';
import CrossSectionLink from '@/components/shared/CrossSectionLink.vue';

const servers = ref<DocsServerSummary[]>([]);
const loading = ref(true);
const search = ref('');

onMounted(async () => {
  try {
    servers.value = await docsApi.list();
  } catch {
    // Silently fail
  } finally {
    loading.value = false;
  }
});

function stripHtml(html: string): string {
  const div = document.createElement('div')
  div.innerHTML = html
  return div.textContent || div.innerText || ''
}

const filteredServers = computed(() => {
  if (!search.value) return servers.value;
  const q = search.value.toLowerCase();
  return servers.value.filter(
    s => s.name.toLowerCase().includes(q) || s.description.toLowerCase().includes(q)
  );
});
</script>
