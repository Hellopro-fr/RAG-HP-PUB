<template>
  <div>
    <PageBreadcrumb page-title="Templates" />

    <p class="text-sm text-gray-500 dark:text-gray-400 -mt-3 mb-6">
      Catalogue de templates MCP prêts à déployer. Choisissez un template pour créer une instance.
    </p>

    <!-- Loading (initial load only) -->
    <div
      v-if="templatesStore.isLoading && templatesStore.templates.length === 0"
      class="text-center py-12"
    >
      <i class="pi pi-spinner pi-spin text-2xl text-brand-500" />
    </div>

    <!-- Empty state -->
    <div
      v-else-if="templatesStore.templates.length === 0"
      class="text-center py-12 text-gray-500 dark:text-gray-400"
    >
      <i class="pi pi-th-large text-4xl mb-3 block" />
      <p>Aucun template disponible</p>
    </div>

    <!-- Grid of template cards -->
    <div
      v-else
      class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4"
    >
      <router-link
        v-for="template in templatesStore.templates"
        :key="template.slug"
        :to="{ name: 'template-detail', params: { slug: template.slug } }"
        class="block bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-800 shadow-theme-xs hover:shadow-theme-md hover:border-brand-300 dark:hover:border-brand-500/40 transition-all p-5"
      >
        <!-- Row 1: icon + name + instance count -->
        <div class="flex items-start justify-between gap-3">
          <div class="flex items-center gap-3 min-w-0">
            <div
              v-if="template.icon"
              class="w-10 h-10 rounded-full bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 flex items-center justify-center shrink-0 p-1"
            >
              <img :src="template.icon" :alt="template.name" class="w-7 h-7 object-contain" />
            </div>
            <div
              v-else
              class="w-10 h-10 rounded-full bg-brand-50 dark:bg-brand-500/15 text-brand-500 flex items-center justify-center shrink-0"
            >
              <i class="pi pi-th-large text-lg" />
            </div>
            <h3 class="text-sm font-semibold text-gray-900 dark:text-white truncate">
              {{ template.name }}
            </h3>
          </div>
          <span
            class="text-xs px-2 py-0.5 rounded-full font-medium shrink-0 bg-brand-50 dark:bg-brand-500/10 text-brand-600 dark:text-brand-400"
          >
            {{ template.instance_count }} instance{{ template.instance_count > 1 ? 's' : '' }}
          </span>
        </div>

        <!-- Description -->
        <p
          v-if="template.description"
          class="mt-3 text-xs text-gray-500 dark:text-gray-400 line-clamp-2"
        >
          {{ template.description }}
        </p>

        <!-- Stdio command -->
        <p
          v-if="template.stdio_command"
          class="mt-3 text-xs font-mono text-gray-600 dark:text-gray-400 bg-gray-50 dark:bg-white/5 px-2 py-1 rounded truncate"
          :title="template.stdio_command"
        >
          {{ template.stdio_command }}
        </p>

        <!-- Tags -->
        <div
          v-if="template.tags && template.tags.length > 0"
          class="mt-3 flex flex-wrap gap-1"
        >
          <span
            v-for="tag in template.tags"
            :key="tag"
            class="text-xs bg-gray-100 dark:bg-white/5 text-gray-600 dark:text-gray-400 px-2 py-0.5 rounded-full"
          >
            {{ tag }}
          </span>
        </div>
      </router-link>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { useTemplatesStore } from '@/stores/templates'
import PageBreadcrumb from '@/components/common/PageBreadcrumb.vue'

const templatesStore = useTemplatesStore()

onMounted(() => {
  templatesStore.fetchTemplates()
})
</script>