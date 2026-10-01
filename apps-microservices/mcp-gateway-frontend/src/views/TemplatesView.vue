<template>
  <div>
    <PageBreadcrumb page-title="Templates" />

    <div class="-mt-3 mb-6 flex items-start justify-between gap-4 flex-wrap">
      <p class="text-sm text-gray-500 dark:text-gray-400 max-w-2xl">
        Catalogue de templates MCP prêts à déployer. Choisissez un template pour créer une instance.
      </p>
      <!-- Admin-only catalog import/export. Exports include inactive templates
           so a round-trip restores exact catalog state; instances/credentials
           are never part of either payload. -->
      <div v-if="authStore.isAdmin" class="flex gap-2 shrink-0">
        <button
          type="button"
          class="inline-flex items-center gap-2 px-3 py-1.5 text-xs font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-md hover:bg-gray-50 dark:hover:bg-white/5 disabled:opacity-50 disabled:cursor-not-allowed"
          :disabled="exporting"
          @click="onExport"
        >
          <i class="pi pi-download text-[11px]" />
          {{ exporting ? 'Export…' : 'Exporter' }}
        </button>
        <button
          type="button"
          class="inline-flex items-center gap-2 px-3 py-1.5 text-xs font-medium text-white bg-brand-500 hover:bg-brand-600 rounded-md"
          @click="importOpen = true"
        >
          <i class="pi pi-upload text-[11px]" />
          Importer
        </button>
      </div>
    </div>

    <p
      v-if="exportError"
      class="mb-4 rounded-md bg-error-50 dark:bg-error-500/15 px-3 py-2 text-xs text-error-600 dark:text-error-400"
    >
      <i class="pi pi-exclamation-triangle text-[11px] mr-1" />
      {{ exportError }}
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
        :to="templateTarget(template)"
        class="block bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-800 shadow-theme-xs hover:shadow-theme-md hover:border-brand-300 dark:hover:border-brand-500/40 transition-all p-5"
      >
        <!-- Row 1: icon + name + kind badge + instance count -->
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
          <div class="flex items-center gap-1.5 shrink-0">
            <span
              v-if="template.kind === 'http_batch'"
              class="text-xs px-2 py-0.5 rounded-full font-medium bg-brand-500 text-white dark:bg-brand-500"
              title="Import HTTP en masse depuis Google Sheets"
            >
              HTTP
            </span>
            <span
              v-else
              class="text-xs px-2 py-0.5 rounded-full font-medium bg-brand-50 dark:bg-brand-500/10 text-brand-600 dark:text-brand-400"
            >
              {{ template.instance_count }} instance{{ template.instance_count > 1 ? 's' : '' }}
            </span>
          </div>
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

    <ImportTemplatesModal
      v-model:open="importOpen"
      @imported="templatesStore.fetchTemplates()"
    />
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import type { RouteLocationRaw } from 'vue-router'
import { useTemplatesStore } from '@/stores/templates'
import { useAuthStore } from '@/stores/auth'
import PageBreadcrumb from '@/components/common/PageBreadcrumb.vue'
import ImportTemplatesModal from '@/components/templates/ImportTemplatesModal.vue'
import { ApiError } from '@/types/api'
import type { Template } from '@/types/templates'

const templatesStore = useTemplatesStore()
const authStore = useAuthStore()

const importOpen = ref(false)
const exporting = ref(false)
const exportError = ref('')

onMounted(() => {
  templatesStore.fetchTemplates()
})

// isZohoSlug returns true for any Zoho template slug so that those cards
// always route to the template-detail view (which renders ZohoImportsSection)
// rather than being redirected straight to the Google Sheets import wizard.
function isZohoSlug(slug: string): boolean {
  return slug === 'zoho' || slug.startsWith('zoho-')
}

// templateTarget routes a catalog card based on its kind:
//   - http_batch + Zoho slug → template-detail (Zoho branch with ZohoImportsSection)
//   - http_batch (non-Zoho)  → the existing Google Sheets server-import flow,
//                              with ?from=templates so the import view's back-link
//                              returns here rather than to /servers, and
//                              ?template_slug=<slug> so the import request stamps
//                              every created mcp_servers row with the originating template.
//   - stdio                  → the usual per-template detail view (instance list / create)
function templateTarget(template: Template): RouteLocationRaw {
  if (template.kind === 'http_batch' && !isZohoSlug(template.slug)) {
    return {
      name: 'google-sheets-import',
      query: { from: 'templates', template_slug: template.slug },
    }
  }
  return { name: 'template-detail', params: { slug: template.slug } }
}

// onExport triggers a browser download of the full catalog. We build a
// temporary <a> + object URL because the backend sets Content-Disposition,
// but fetch() honours that header only for navigations, not XHR — so the
// save-as dialog must be triggered manually.
async function onExport(): Promise<void> {
  exporting.value = true
  exportError.value = ''
  try {
    const blob = await templatesStore.exportCatalog()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    const today = new Date().toISOString().slice(0, 10)
    a.download = `templates-export-${today}.json`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    // Revoke on next tick to ensure the download has started before the URL
    // is invalidated. Browsers keep the blob alive as long as the fetch
    // triggered by the download is in-flight.
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  } catch (e: unknown) {
    if (e instanceof ApiError) {
      const body = e.body as { error?: string } | undefined
      exportError.value = body?.error ?? e.message
    } else if (e instanceof Error) {
      exportError.value = e.message
    } else {
      exportError.value = "Échec de l'export"
    }
  } finally {
    exporting.value = false
  }
}
</script>