<template>
  <div>
    <PageBreadcrumb page-title="Documentation" />

    <!-- Loading -->
    <div v-if="loading" class="text-center py-12">
      <i class="pi pi-spinner pi-spin text-2xl text-brand-500" />
    </div>

    <template v-else>
      <!-- Tabs + Actions bar -->
      <div class="bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-800 shadow-theme-xs overflow-hidden">
        <div class="flex items-center justify-between border-b border-gray-100 dark:border-gray-800">
          <!-- Tabs -->
          <div class="flex items-center">
            <button
              v-for="tab in tabs"
              :key="tab.value"
              class="px-5 py-4 text-sm font-medium transition-colors relative"
              :class="statusFilter === tab.value
                ? 'text-brand-600 dark:text-brand-400'
                : 'text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200'"
              @click="statusFilter = tab.value"
            >
              {{ tab.label }}
              <span
                class="ml-2 inline-flex items-center justify-center min-w-[20px] h-5 px-1.5 text-xs font-medium rounded-full"
                :class="statusFilter === tab.value
                  ? 'bg-brand-100 text-brand-600 dark:bg-brand-500/20 dark:text-brand-400'
                  : 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300'"
              >
                {{ tab.count }}
              </span>
              <span v-if="statusFilter === tab.value" class="absolute bottom-0 left-0 right-0 h-0.5 bg-brand-500" />
            </button>
          </div>

          <!-- Actions -->
          <div class="flex items-center gap-3 px-4">
            <input
              v-model="search"
              type="text"
              placeholder="Rechercher..."
              class="h-9 w-48 rounded-md border border-gray-300 bg-transparent px-3 py-1.5 text-sm text-gray-800 placeholder:text-gray-400 focus:border-brand-300 focus:outline-hidden dark:border-gray-700 dark:bg-gray-900 dark:text-white/90 dark:placeholder:text-white/30"
            />
            <button
              v-if="authStore.isAdmin"
              class="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-200 border border-gray-300 dark:border-gray-600 rounded-md hover:bg-gray-50 dark:hover:bg-gray-700"
              :disabled="generatingSlugs"
              @click="handleGenerateSlugs"
            >
              <i v-if="generatingSlugs" class="pi pi-spinner pi-spin mr-1" />
              Generer slugs
            </button>
            <button
              v-if="authStore.isAdmin"
              class="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-200 border border-gray-300 dark:border-gray-600 rounded-md hover:bg-gray-50 dark:hover:bg-gray-700"
              @click="handleBatchExport"
            >
              Exporter tout
            </button>
            <label
              v-if="authStore.isAdmin"
              class="px-4 py-2 text-sm font-medium text-brand-500 border border-brand-300 rounded-md hover:bg-brand-50 dark:hover:bg-brand-500/10 cursor-pointer"
              :class="dragOverBatch ? 'border-brand-400 bg-brand-50 dark:bg-brand-500/10' : ''"
              @dragover.prevent="dragOverBatch = true"
              @dragleave="dragOverBatch = false"
              @drop.prevent="handleBatchDrop"
            >
              Importer tout
              <input ref="batchInput" type="file" accept=".json" class="hidden" @change="handleBatchImport" />
            </label>
          </div>
        </div>

        <p v-if="batchError" class="text-xs text-error-500 dark:text-error-400 px-4 pt-3">{{ batchError }}</p>
        <p v-if="batchSuccess" class="text-xs text-success-600 dark:text-success-400 px-4 pt-3">{{ batchSuccess }}</p>
        <table class="w-full text-sm">
          <thead>
            <tr class="border-b border-gray-100 dark:border-gray-800">
              <th class="text-left px-4 py-3 text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide">Serveur</th>
              <th class="text-left px-4 py-3 text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide">Slug</th>
              <th class="text-left px-4 py-3 text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide">Statut</th>
              <th class="text-left px-4 py-3 text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide">Outils</th>
              <th class="text-left px-4 py-3 text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide">Config</th>
              <th class="text-right px-4 py-3 text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide">Actions</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-100 dark:divide-gray-800">
            <tr
              v-for="server in filteredServers"
              :key="server.id"
              class="hover:bg-gray-50 dark:hover:bg-white/5"
            >
              <!-- Server name + icon -->
              <td class="px-4 py-3">
                <div class="flex items-center gap-2.5">
                  <img
                    v-if="server.icon"
                    :src="server.icon"
                    :alt="server.name"
                    class="w-6 h-6 rounded object-contain"
                  />
                  <i v-else class="pi pi-server text-sm text-gray-400" />
                  <span class="font-medium text-gray-800 dark:text-gray-200">{{ server.name }}</span>
                </div>
              </td>

              <!-- Slug -->
              <td class="px-4 py-3">
                <code v-if="server.doc_slug" class="text-xs bg-gray-100 dark:bg-white/5 px-1.5 py-0.5 rounded text-gray-600 dark:text-gray-400">
                  /docs/{{ server.doc_slug }}
                </code>
                <span v-else class="text-xs text-gray-400 dark:text-gray-500 italic">Aucun</span>
              </td>

              <!-- Status -->
              <td class="px-4 py-3">
                <span
                  v-if="isPublished(server)"
                  class="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full font-medium bg-success-50 text-success-600 dark:bg-success-500/15 dark:text-success-400"
                >
                  <span class="w-1.5 h-1.5 rounded-full bg-success-500" />
                  Publie
                </span>
                <span
                  v-else
                  class="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full font-medium bg-gray-100 text-gray-500 dark:bg-white/5 dark:text-gray-400"
                >
                  <span class="w-1.5 h-1.5 rounded-full bg-gray-400" />
                  Brouillon
                </span>
              </td>

              <!-- Tools count -->
              <td class="px-4 py-3 text-gray-600 dark:text-gray-400">
                {{ server.tools_count }}
              </td>

              <!-- Has config guide -->
              <td class="px-4 py-3">
                <i
                  v-if="server.doc_config_guide && server.doc_config_guide.steps && server.doc_config_guide.steps.length > 0"
                  class="pi pi-check text-success-500"
                />
                <i v-else class="pi pi-minus text-gray-300 dark:text-gray-600" />
              </td>

              <!-- Actions -->
              <td class="px-4 py-3">
                <div class="flex items-center justify-end gap-1">
                  <button
                    class="p-1.5 rounded hover:bg-gray-100 dark:hover:bg-white/5"
                    :class="server.is_active
                      ? 'text-success-500 hover:text-orange-500'
                      : 'text-gray-400 hover:text-success-500'"
                    :title="server.is_active ? 'Desactiver' : 'Activer'"
                    @click="handleToggle(server.id, !server.is_active)"
                  >
                    <i :class="server.is_active ? 'pi pi-eye' : 'pi pi-eye-slash'" class="text-sm" />
                  </button>
                  <router-link
                    :to="`/servers/${server.id}/documentation`"
                    class="p-1.5 rounded hover:bg-gray-100 dark:hover:bg-white/5 text-gray-500 dark:text-gray-400"
                    title="Modifier la documentation"
                  >
                    <i class="pi pi-pencil text-sm" />
                  </router-link>
                  <a
                    v-if="server.doc_slug"
                    :href="`/docs/${server.doc_slug}`"
                    target="_blank"
                    class="p-1.5 rounded hover:bg-gray-100 dark:hover:bg-white/5 text-brand-500 dark:text-brand-400"
                    title="Voir sur /docs"
                  >
                    <i class="pi pi-external-link text-sm" />
                  </a>
                </div>
              </td>
            </tr>
          </tbody>
        </table>

        <!-- Empty -->
        <div v-if="filteredServers.length === 0" class="text-center py-12 text-gray-500 dark:text-gray-400">
          <i class="pi pi-book text-4xl mb-3 block" />
          <p>Aucun serveur trouvé</p>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useServersStore } from '@/stores/servers'
import { useAuthStore } from '@/stores/auth'
import { useToast } from '@/composables/useToast'
import { api } from '@/api/client'
import { serversApi } from '@/api/servers'
import PageBreadcrumb from '@/components/common/PageBreadcrumb.vue'
import type { Server } from '@/types/server'

const serversStore = useServersStore()
const authStore = useAuthStore()
const toast = useToast()

const loading = ref(true)
const search = ref('')
const statusFilter = ref('all')
const generatingSlugs = ref(false)
const dragOverBatch = ref(false)
const batchError = ref('')
const batchSuccess = ref('')

onMounted(async () => {
  await serversStore.fetchServers()
  loading.value = false
})

const tabs = computed(() => {
  const all = serversStore.servers
  const published = all.filter(s => s.is_active && !!s.doc_slug)
  const draft = all.filter(s => !s.is_active || !s.doc_slug)
  return [
    { label: 'Tous', value: 'all', count: all.length },
    { label: 'Publie', value: 'published', count: published.length },
    { label: 'Brouillon', value: 'draft', count: draft.length },
  ]
})

function isPublished(server: Server): boolean {
  return server.is_active && !!server.doc_slug
}

const filteredServers = computed(() => {
  let list = serversStore.servers
  if (search.value) {
    const q = search.value.toLowerCase()
    list = list.filter(s =>
      s.name.toLowerCase().includes(q) ||
      (s.doc_slug && s.doc_slug.toLowerCase().includes(q))
    )
  }
  if (statusFilter.value === 'published') {
    list = list.filter(s => isPublished(s))
  } else if (statusFilter.value === 'draft') {
    list = list.filter(s => !isPublished(s))
  }
  return list
})

async function handleToggle(id: string, enable: boolean) {
  try {
    if (enable) {
      await serversApi.enable(id)
    } else {
      await serversApi.disable(id)
    }
    await serversStore.fetchServers()
    toast.success(enable ? 'Documentation activee' : 'Documentation desactivee')
  } catch (err) {
    toast.error(err instanceof Error ? err.message : 'Erreur')
  }
}

async function handleGenerateSlugs() {
  generatingSlugs.value = true
  try {
    const res = await api.post<{ updated: number }>('/api/v1/servers/generate-slugs')
    if (res.updated > 0) {
      toast.success(`${res.updated} slug(s) genere(s)`)
      await serversStore.fetchServers()
    } else {
      toast.success('Tous les serveurs ont deja un slug')
    }
  } catch (err) {
    toast.error(err instanceof Error ? err.message : 'Erreur')
  } finally {
    generatingSlugs.value = false
  }
}

function handleBatchExport() {
  const data = serversStore.servers
    .filter(s => s.doc_slug)
    .map(s => ({
      server_name: s.name,
      doc_slug: s.doc_slug,
      doc_description: s.doc_description || '',
      doc_config_guide: s.doc_config_guide || { authType: '', steps: [] }
    }))

  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'docs-export.json'
  a.click()
  URL.revokeObjectURL(url)
}

function handleBatchDrop(event: DragEvent) {
  dragOverBatch.value = false
  const file = event.dataTransfer?.files?.[0]
  if (!file || !file.name.endsWith('.json')) {
    batchError.value = 'Fichier JSON attendu'
    return
  }
  processBatchFile(file)
}

function handleBatchImport(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  processBatchFile(file)
  input.value = ''
}

async function processBatchFile(file: File) {
  batchError.value = ''
  batchSuccess.value = ''

  const text = await file.text()
  let data: unknown
  try {
    data = JSON.parse(text)
  } catch {
    batchError.value = 'Fichier JSON invalide'
    return
  }

  const entries = Array.isArray(data) ? data : [data]
  let updated = 0
  let skipped = 0
  const skippedNames: string[] = []

  for (const entry of entries) {
    if (!entry.server_name && !entry.doc_slug) {
      skipped++
      continue
    }

    // Find matching server by name, slug, or slugified name
    const entryName = (entry.server_name || '').toLowerCase().trim()
    const entrySlug = (entry.doc_slug || '').toLowerCase().trim()
    const slugify = (s: string) => s.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '')
    const entryNameSlug = entryName ? slugify(entryName) : ''

    const server = serversStore.servers.find(s => {
      const sName = s.name.toLowerCase().trim()
      const sSlug = (s.doc_slug || '').toLowerCase().trim()
      const sNameSlug = slugify(s.name)

      // Exact name or slug match
      if (entryName && sName === entryName) return true
      if (entrySlug && sSlug === entrySlug) return true
      // Slug in server's auto-generated slug (which has a hash suffix)
      if (entrySlug && sSlug.startsWith(entrySlug)) return true
      // Slugified entry name matches start of server slug
      if (entryNameSlug && sSlug.startsWith(entryNameSlug)) return true
      // Slugified server name matches entry slug
      if (entrySlug && sNameSlug === entrySlug) return true
      if (entrySlug && sNameSlug.startsWith(entrySlug)) return true
      // Partial name match
      if (entryName && (sName.includes(entryName) || entryName.includes(sName))) return true
      // Slugified names match
      if (entryNameSlug && sNameSlug === entryNameSlug) return true
      return false
    })

    if (!server) {
      skipped++
      skippedNames.push(entry.server_name || entry.doc_slug || '?')
      continue
    }

    try {
      await serversApi.update(server.id, {
        doc_slug: entry.doc_slug ?? server.doc_slug ?? '',
        doc_description: entry.doc_description ?? '',
        doc_config_guide: entry.doc_config_guide ?? { authType: '', steps: [] }
      } as any)
      updated++
    } catch (err: any) {
      skipped++
      const errMsg = err?.body?.error || ''
      skippedNames.push((entry.server_name || entry.doc_slug || '?') + (errMsg ? ` (${errMsg})` : ''))
    }
  }

  await serversStore.fetchServers()
  batchSuccess.value = `${updated} documentation(s) importee(s)` + (skipped > 0 ? `, ${skipped} ignoree(s): ${skippedNames.join(', ')}` : '')
}
</script>
