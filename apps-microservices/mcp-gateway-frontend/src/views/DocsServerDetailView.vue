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

    <CrossSectionLink
      to="/install-guide"
      icon="pi-download"
      message="Configurez votre client MCP pour acceder a ces outils."
      link-label="Suivre le guide d'installation"
    />

    <!-- Loading skeleton -->
    <div v-if="loading" class="animate-pulse" aria-hidden="true">
      <div class="mb-8">
        <div class="flex items-center gap-4">
          <div class="w-10 h-10 rounded bg-gray-200 dark:bg-gray-800" />
          <div class="h-7 w-1/3 rounded bg-gray-200 dark:bg-gray-800" />
        </div>
        <div class="mt-3 space-y-2">
          <div class="h-3 w-5/6 rounded bg-gray-100 dark:bg-gray-800" />
          <div class="h-3 w-2/3 rounded bg-gray-100 dark:bg-gray-800" />
        </div>
        <div class="mt-4 h-3 w-24 rounded bg-gray-100 dark:bg-gray-800" />
      </div>
      <div class="h-5 w-32 rounded bg-gray-200 dark:bg-gray-800 mb-4" />
      <div class="space-y-4">
        <div
          v-for="i in 3"
          :key="i"
          class="rounded-lg border border-gray-200 dark:border-gray-800 p-4"
        >
          <div class="h-4 w-1/4 rounded bg-gray-200 dark:bg-gray-800 mb-2" />
          <div class="h-3 w-5/6 rounded bg-gray-100 dark:bg-gray-800" />
        </div>
      </div>
    </div>

    <!-- Not found -->
    <div v-else-if="!server" class="text-center py-16">
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
        <div class="flex items-center gap-4">
          <img
            v-if="server.icon"
            :src="server.icon"
            :alt="server.name"
            class="w-10 h-10 flex-shrink-0 rounded"
          />
          <h1 class="text-2xl font-bold text-gray-900 dark:text-white">{{ server.name }}</h1>
        </div>
        <div v-if="server.description" class="docs-html-content mt-1" v-html="server.description" />
        <div class="mt-3 text-sm text-gray-500 dark:text-gray-400">
          {{ server.tools_count }} outil{{ server.tools_count !== 1 ? 's' : '' }}
        </div>
      </div>

      <!-- Config Guide -->
      <section
        v-if="server.config_guide && server.config_guide.steps && server.config_guide.steps.length > 0"
        id="configuration"
        class="mb-8 scroll-mt-20"
      >
        <h2 class="group text-lg font-semibold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
          <a href="#configuration" class="inline-flex items-center gap-1.5 hover:underline">
            Configuration
            <i class="pi pi-link text-xs text-gray-400 dark:text-gray-500 opacity-0 group-hover:opacity-100 transition-opacity" />
          </a>
          <span class="inline-flex items-center px-2 py-0.5 text-xs font-medium rounded-full bg-brand-100 text-brand-700 dark:bg-brand-900/30 dark:text-brand-300">
            {{ server.config_guide.authType }}
          </span>
        </h2>
        <div class="space-y-4">
          <template v-for="(step, index) in server.config_guide.steps" :key="index">
            <!-- Step element -->
            <div v-if="!step.type || step.type === 'step'" class="flex gap-3">
              <span class="flex-shrink-0 w-7 h-7 rounded-full bg-brand-500 text-white text-sm font-semibold flex items-center justify-center">
                {{ stepNumber(index) }}
              </span>
              <div class="pt-0.5">
                <p class="font-medium text-gray-900 dark:text-white text-sm">{{ step.title }}</p>
                <div class="text-sm text-gray-600 dark:text-gray-400 mt-0.5 doc-step-body" v-html="step.description" />
                <a
                  v-if="step.link"
                  :href="step.link"
                  target="_blank"
                  rel="noopener noreferrer"
                  class="inline-flex items-center gap-1 mt-1 text-xs text-brand-500 hover:text-brand-600 dark:text-brand-400"
                >
                  {{ step.link }}
                  <svg class="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M13.5 6H5.25A2.25 2.25 0 003 8.25v10.5A2.25 2.25 0 005.25 21h10.5A2.25 2.25 0 0018 18.75V10.5m-10.5 6L21 3m0 0h-5.25M21 3v5.25" />
                  </svg>
                </a>
                <img
                  v-if="step.image"
                  :src="step.image"
                  :alt="step.title"
                  class="mt-3 rounded-lg border border-gray-200 dark:border-gray-700 max-w-full shadow-sm"
                />
              </div>
            </div>

            <!-- Text element -->
            <div
              v-else-if="step.type === 'text'"
              class="text-sm text-gray-700 dark:text-gray-300 doc-step-body"
              v-html="step.description"
            />

            <!-- Image element -->
            <img
              v-else-if="step.type === 'image' && step.image"
              :src="step.image"
              :alt="step.title"
              class="rounded-lg border border-gray-200 dark:border-gray-700 max-w-full shadow-sm"
            />

            <!-- Link element -->
            <a
              v-else-if="step.type === 'link' && step.link"
              :href="step.link"
              target="_blank"
              rel="noopener noreferrer"
              class="inline-flex items-center gap-1.5 text-sm text-brand-500 hover:text-brand-600 dark:text-brand-400"
            >
              <svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                <path stroke-linecap="round" stroke-linejoin="round" d="M13.5 6H5.25A2.25 2.25 0 003 8.25v10.5A2.25 2.25 0 005.25 21h10.5A2.25 2.25 0 0018 18.75V10.5m-10.5 6L21 3m0 0h-5.25M21 3v5.25" />
              </svg>
              {{ step.title || step.link }}
            </a>

            <!-- Divider element -->
            <hr v-else-if="step.type === 'divider'" class="border-gray-200 dark:border-gray-700" />
          </template>
        </div>
      </section>

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
      <section v-if="filteredTools.length > 0" id="tools" class="scroll-mt-20">
        <h2 class="group text-lg font-semibold text-gray-900 dark:text-white mb-4">
          <a href="#tools" class="inline-flex items-center gap-1.5 hover:underline">
            Outils
            <i class="pi pi-link text-xs text-gray-400 dark:text-gray-500 opacity-0 group-hover:opacity-100 transition-opacity" />
          </a>
        </h2>
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
import { ref, computed, onMounted, nextTick } from 'vue';
import { useRoute } from 'vue-router';
import { docsApi } from '@/api/docs';
import type { DocsServerDetail } from '@/types/docs';
import ToolDocCard from '@/components/docs/ToolDocCard.vue';
import CrossSectionLink from '@/components/shared/CrossSectionLink.vue';

const route = useRoute();
const slug = route.params.serverSlug as string;
const server = ref<DocsServerDetail | null>(null);
const loading = ref(true);
const toolSearch = ref('');

onMounted(async () => {
  try {
    server.value = await docsApi.get(slug);
  } catch {
    server.value = null;
  } finally {
    loading.value = false;
  }
  // The page data loads asynchronously after mount, so the browser's native
  // anchor-scroll has already run when the target <section> didn't exist yet.
  // Re-trigger the scroll once the DOM is up-to-date.
  if (route.hash) {
    await nextTick()
    const id = route.hash.slice(1)
    const el = document.getElementById(id)
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }
});

// Compute step number (only counting step-type elements, not text/image/divider)
function stepNumber(index: number): number {
  if (!server.value?.config_guide) return index + 1
  let count = 0
  for (let i = 0; i <= index; i++) {
    const s = server.value.config_guide.steps[i]
    if (!s?.type || s.type === 'step') count++
  }
  return count
}

const filteredTools = computed(() => {
  if (!server.value) return [];
  if (!toolSearch.value) return server.value.tools;
  const q = toolSearch.value.toLowerCase();
  return server.value.tools.filter(
    t => t.name.toLowerCase().includes(q) || (t.description && t.description.toLowerCase().includes(q))
  );
});
</script>

<style scoped>
/* Render HTML from rich-text step descriptions with sensible defaults. */
.doc-step-body :deep(ul) { list-style: disc; margin-left: 1.25rem; margin-top: 0.35rem; }
.doc-step-body :deep(ol) { list-style: decimal; margin-left: 1.25rem; margin-top: 0.35rem; }
.doc-step-body :deep(li) { margin-top: 0.15rem; }
.doc-step-body :deep(strong) { font-weight: 600; color: inherit; }
.doc-step-body :deep(em) { font-style: italic; }
.doc-step-body :deep(p) { margin-top: 0.35rem; }
.doc-step-body :deep(p:first-child) { margin-top: 0; }
.doc-step-body :deep(a) { color: rgb(var(--color-brand-500) / 1); text-decoration: underline; }
.doc-step-body :deep(code) {
  background: rgb(0 0 0 / 0.05);
  padding: 0.1rem 0.35rem;
  border-radius: 0.25rem;
  font-size: 0.85em;
}
</style>
