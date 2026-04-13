<template>
  <div>
    <!-- Breadcrumb -->
    <nav class="mb-6 text-sm">
      <router-link to="/docs" class="text-brand-500 hover:text-brand-600 dark:text-brand-400">
        Documentation
      </router-link>
      <span class="mx-2 text-gray-400">/</span>
      <span class="text-gray-600 dark:text-gray-300">{{ server?.name || '...' }}</span>
    </nav>

    <!-- Not found -->
    <div v-if="!server" class="text-center py-16">
      <div class="w-16 h-16 mx-auto mb-4 rounded-full bg-red-50 dark:bg-red-900/20 flex items-center justify-center">
        <svg class="w-8 h-8 text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
          <path stroke-linecap="round" stroke-linejoin="round" d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z" />
        </svg>
      </div>
      <p class="text-gray-600 dark:text-gray-400 mb-4">Serveur introuvable.</p>
      <router-link
        to="/docs"
        class="inline-block px-4 py-2 text-sm font-medium text-brand-500 border border-brand-300 rounded-md hover:bg-brand-50 dark:hover:bg-brand-500/10"
      >
        Retour a la liste
      </router-link>
    </div>

    <!-- Server detail -->
    <div v-else>
      <!-- Header -->
      <div class="mb-8">
        <h1 class="text-2xl font-bold text-gray-900 dark:text-white">{{ server.name }}</h1>
        <p v-if="server.description" class="text-sm text-gray-500 dark:text-gray-400 mt-1">
          {{ server.description }}
        </p>
        <div class="mt-3 text-sm text-gray-500 dark:text-gray-400">
          {{ server.toolsCount }} outil{{ server.toolsCount !== 1 ? 's' : '' }}
        </div>
      </div>

      <!-- Search tools -->
      <div v-if="server.tools.length > 3" class="mb-6">
        <input
          v-model="toolSearch"
          type="text"
          placeholder="Rechercher un outil..."
          class="w-full max-w-md px-3 py-2 text-sm border border-gray-300 rounded-md bg-white dark:bg-gray-800 dark:border-gray-600 dark:text-gray-200 placeholder:text-gray-400"
        />
      </div>

      <!-- Tools list -->
      <section v-if="filteredTools.length > 0">
        <h2 class="text-lg font-semibold text-gray-900 dark:text-white mb-4">Outils</h2>
        <div class="space-y-4">
          <ToolDocCard
            v-for="tool in filteredTools"
            :key="tool.name"
            :tool="tool"
          />
        </div>
      </section>

      <div v-else-if="toolSearch" class="py-8">
        <p class="text-sm text-gray-400 dark:text-gray-500 italic">
          Aucun outil ne correspond a "{{ toolSearch }}".
        </p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue';
import { useRoute } from 'vue-router';
import { getServerBySlug } from '@/data/servers';
import ToolDocCard from '@/components/docs/ToolDocCard.vue';

const route = useRoute();
const slug = route.params.serverSlug as string;
const server = getServerBySlug(slug) || null;
const toolSearch = ref('');

const filteredTools = computed(() => {
  if (!server) return [];
  if (!toolSearch.value) return server.tools;
  const q = toolSearch.value.toLowerCase();
  return server.tools.filter(
    t => t.name.toLowerCase().includes(q) || (t.description && t.description.toLowerCase().includes(q))
  );
});
</script>
