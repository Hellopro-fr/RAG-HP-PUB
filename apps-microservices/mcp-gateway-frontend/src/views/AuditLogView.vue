<template>
  <div>
    <PageBreadcrumb page-title="Journal d'audit" />

    <!-- Filters -->
    <FilterPanel
      :active-count="activeFilterCount"
      @reset="handleReset"
    >
      <label class="flex flex-col gap-1 text-sm">
        <span class="text-gray-600 dark:text-gray-400">Email utilisateur</span>
        <input v-model="filterEmail" type="text" placeholder="Email" class="px-3 py-2 text-sm border border-gray-300 rounded-md bg-white dark:bg-gray-800 dark:border-gray-600 dark:text-gray-200" />
      </label>
      <label class="flex flex-col gap-1 text-sm">
        <span class="text-gray-600 dark:text-gray-400">Action</span>
        <input v-model="filterAction" type="text" placeholder="Action" class="px-3 py-2 text-sm border border-gray-300 rounded-md bg-white dark:bg-gray-800 dark:border-gray-600 dark:text-gray-200" />
      </label>
      <label class="flex flex-col gap-1 text-sm">
        <span class="text-gray-600 dark:text-gray-400">Ressource</span>
        <select v-model="filterResourceType" class="px-3 py-2 text-sm border border-gray-300 rounded-md bg-white dark:bg-gray-800 dark:border-gray-600 dark:text-gray-200">
          <option value="">Toutes</option>
          <option value="servers">Serveurs</option>
          <option value="tokens">Jetons</option>
          <option value="oauth2_clients">Clients OAuth2</option>
          <option value="users">Utilisateurs</option>
          <option value="mcp_transport">Transport MCP</option>
        </select>
      </label>
      <label class="flex flex-col gap-1 text-sm">
        <span class="text-gray-600 dark:text-gray-400">Méthode</span>
        <select v-model="clientFilters.method" class="px-3 py-2 text-sm border border-gray-300 rounded-md bg-white dark:bg-gray-800 dark:border-gray-600 dark:text-gray-200">
          <option value="">Toutes</option>
          <option value="GET">GET</option>
          <option value="POST">POST</option>
          <option value="PUT">PUT</option>
          <option value="PATCH">PATCH</option>
          <option value="DELETE">DELETE</option>
        </select>
      </label>
      <label class="flex flex-col gap-1 text-sm">
        <span class="text-gray-600 dark:text-gray-400">Statut HTTP</span>
        <select v-model="clientFilters.statusBucket" class="px-3 py-2 text-sm border border-gray-300 rounded-md bg-white dark:bg-gray-800 dark:border-gray-600 dark:text-gray-200">
          <option value="">Tous</option>
          <option value="2xx">2xx Succès</option>
          <option value="3xx">3xx Redirection</option>
          <option value="4xx">4xx Client</option>
          <option value="5xx">5xx Serveur</option>
        </select>
      </label>
      <label class="flex flex-col gap-1 text-sm">
        <span class="text-gray-600 dark:text-gray-400">IP</span>
        <input v-model="clientFilters.ip" type="text" placeholder="Adresse IP" class="px-3 py-2 text-sm border border-gray-300 rounded-md bg-white dark:bg-gray-800 dark:border-gray-600 dark:text-gray-200" />
      </label>
      <label class="flex flex-col gap-1 text-sm">
        <span class="text-gray-600 dark:text-gray-400">Date début</span>
        <input v-model="filterDateFrom" type="date" class="px-3 py-2 text-sm border border-gray-300 rounded-md bg-white dark:bg-gray-800 dark:border-gray-600 dark:text-gray-200" />
      </label>
      <label class="flex flex-col gap-1 text-sm">
        <span class="text-gray-600 dark:text-gray-400">Date fin</span>
        <input v-model="filterDateTo" type="date" class="px-3 py-2 text-sm border border-gray-300 rounded-md bg-white dark:bg-gray-800 dark:border-gray-600 dark:text-gray-200" />
      </label>
      <div class="sm:col-span-2 lg:col-span-3 flex items-end">
        <button
          class="px-4 py-2 text-sm font-medium text-white bg-brand-500 rounded-md hover:bg-brand-600"
          @click="applyFilter"
        >
          <i class="pi pi-filter mr-1" />
          Appliquer (serveur)
        </button>
      </div>
    </FilterPanel>

    <!-- Table container -->
    <div class="rounded-2xl border border-gray-200 bg-white dark:border-gray-800 dark:bg-white/[0.03] overflow-hidden">
      <!-- Loading -->
      <div v-if="loading" class="text-center py-12">
        <i class="pi pi-spinner pi-spin text-2xl text-brand-500" />
      </div>

      <template v-else-if="filteredLogs.length">
        <div class="overflow-x-auto">
          <table class="w-full text-sm">
            <thead>
              <tr class="border-b border-gray-100 dark:border-gray-800 bg-gray-50 dark:bg-white/[0.02]">
                <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">
                  Date
                </th>
                <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">
                  Utilisateur
                </th>
                <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">
                  Action
                </th>
                <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">
                  Ressource
                </th>
                <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">
                  Statut
                </th>
                <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide">
                  IP
                </th>
              </tr>
            </thead>
            <tbody class="divide-y divide-gray-100 dark:divide-gray-800">
              <template v-for="log in filteredLogs" :key="log.id">
                <!-- Main row -->
                <tr
                  class="hover:bg-gray-50 dark:hover:bg-white/[0.02] cursor-pointer"
                  @click="toggleExpanded(log.id)"
                >
                  <td class="px-4 py-3 text-gray-700 dark:text-gray-300 whitespace-nowrap">
                    <i
                      class="pi mr-2 text-xs text-gray-400"
                      :class="expandedIds.has(log.id) ? 'pi-chevron-down' : 'pi-chevron-right'"
                    />
                    {{ formatDate(log.created_at) }}
                  </td>
                  <td class="px-4 py-3 text-gray-700 dark:text-gray-300 max-w-[160px] truncate">
                    {{ log.user_email }}
                  </td>
                  <td class="px-4 py-3">
                    <code class="text-xs bg-gray-100 dark:bg-gray-700 text-gray-800 dark:text-gray-200 px-1.5 py-0.5 rounded">
                      {{ log.request_method }} {{ log.action }}
                    </code>
                  </td>
                  <td class="px-4 py-3 text-gray-700 dark:text-gray-300">
                    <span v-if="log.resource_type" class="capitalize">{{ log.resource_type }}</span>
                    <span v-if="log.resource_id" class="text-gray-400 dark:text-gray-500 ml-1">#{{ log.resource_id }}</span>
                  </td>
                  <td class="px-4 py-3">
                    <span
                      class="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium"
                      :class="statusBadgeClass(log.response_status)"
                    >
                      {{ log.response_status }}
                    </span>
                  </td>
                  <td class="px-4 py-3 text-gray-500 dark:text-gray-400 font-mono text-xs">
                    {{ log.ip_address }}
                  </td>
                </tr>
                <!-- Expanded detail row -->
                <tr v-if="expandedIds.has(log.id)">
                  <td colspan="6" class="px-4 pb-4 pt-0 bg-gray-50 dark:bg-white/[0.02]">
                    <div class="grid grid-cols-1 md:grid-cols-2 gap-3 mt-1">
                      <div v-if="log.request_body">
                        <p class="text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">Corps de la requête</p>
                        <pre class="text-xs bg-gray-100 dark:bg-gray-900 rounded p-3 overflow-x-auto text-gray-800 dark:text-gray-200 max-h-48">{{ formatJson(log.request_body) }}</pre>
                      </div>
                      <div v-if="log.response_body">
                        <p class="text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">Corps de la réponse</p>
                        <pre class="text-xs bg-gray-100 dark:bg-gray-900 rounded p-3 overflow-x-auto text-gray-800 dark:text-gray-200 max-h-48">{{ formatJson(log.response_body) }}</pre>
                      </div>
                      <div v-if="!log.request_body && !log.response_body" class="col-span-2">
                        <p class="text-xs text-gray-400 dark:text-gray-500 italic">Aucun détail disponible</p>
                      </div>
                    </div>
                    <p class="text-xs text-gray-400 dark:text-gray-500 mt-2 font-mono">
                      {{ log.request_method }} {{ log.request_path }}
                    </p>
                  </td>
                </tr>
              </template>
            </tbody>
          </table>
        </div>

        <!-- Pagination -->
        <div class="flex items-center justify-between px-4 py-3 border-t border-gray-100 dark:border-gray-800">
          <p class="text-sm text-gray-500 dark:text-gray-400">
            Page {{ currentPage }} sur {{ totalPages }} — {{ total }} entrées
          </p>
          <div class="flex items-center gap-2">
            <button
              :disabled="currentPage <= 1"
              class="px-3 py-1.5 text-sm font-medium text-gray-700 dark:text-gray-200 border border-gray-300 dark:border-gray-600 rounded-md hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-40 disabled:cursor-not-allowed"
              @click="goToPage(currentPage - 1)"
            >
              <i class="pi pi-chevron-left" />
              Précédent
            </button>
            <button
              :disabled="currentPage >= totalPages"
              class="px-3 py-1.5 text-sm font-medium text-gray-700 dark:text-gray-200 border border-gray-300 dark:border-gray-600 rounded-md hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-40 disabled:cursor-not-allowed"
              @click="goToPage(currentPage + 1)"
            >
              Suivant
              <i class="pi pi-chevron-right" />
            </button>
          </div>
        </div>
      </template>

      <!-- Empty state -->
      <div
        v-else
        class="text-center py-12 text-gray-500 dark:text-gray-400"
      >
        <i class="pi pi-list text-4xl mb-3 block" />
        <p class="font-medium">Aucune entrée dans le journal</p>
        <p class="text-sm mt-1">{{ activeFilterCount > 0 ? 'Aucune entrée ne correspond aux filtres.' : 'Modifiez les filtres ou revenez plus tard.' }}</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { auditApi } from '@/api/audit'
import { useToast } from '@/composables/useToast'
import PageBreadcrumb from '@/components/common/PageBreadcrumb.vue'
import FilterPanel from '@/components/shared/FilterPanel.vue'
import type { AuditLog } from '@/types/audit'

const route = useRoute()
const toast = useToast()

const logs = ref<AuditLog[]>([])
const loading = ref(false)
const total = ref(0)
const currentPage = ref(1)
const totalPages = ref(1)
const expandedIds = ref<Set<number>>(new Set())

const PER_PAGE = 50

// Server-side filter state — pre-populate from query params
const filterEmail = ref((route.query.user_email as string) || '')
const filterAction = ref('')
const filterResourceType = ref('')
const filterDateFrom = ref('')
const filterDateTo = ref('')

// Client-side filter state (applied to the already-fetched page)
const clientFilters = reactive({
  method: '',
  statusBucket: '' as '' | '2xx' | '3xx' | '4xx' | '5xx',
  ip: '',
})

function matchesStatusBucket(status: number, bucket: string): boolean {
  if (!bucket) return true
  if (bucket === '2xx') return status >= 200 && status < 300
  if (bucket === '3xx') return status >= 300 && status < 400
  if (bucket === '4xx') return status >= 400 && status < 500
  if (bucket === '5xx') return status >= 500 && status < 600
  return true
}

const filteredLogs = computed(() => {
  const ip = clientFilters.ip.trim().toLowerCase()
  return logs.value.filter(log => {
    if (clientFilters.method && log.request_method !== clientFilters.method) return false
    if (!matchesStatusBucket(log.response_status, clientFilters.statusBucket)) return false
    if (ip && !log.ip_address.toLowerCase().includes(ip)) return false
    return true
  })
})

const activeFilterCount = computed(() => {
  let n = 0
  if (filterEmail.value) n++
  if (filterAction.value) n++
  if (filterResourceType.value) n++
  if (filterDateFrom.value) n++
  if (filterDateTo.value) n++
  if (clientFilters.method) n++
  if (clientFilters.statusBucket) n++
  if (clientFilters.ip.trim()) n++
  return n
})

function handleReset() {
  filterEmail.value = ''
  filterAction.value = ''
  filterResourceType.value = ''
  filterDateFrom.value = ''
  filterDateTo.value = ''
  clientFilters.method = ''
  clientFilters.statusBucket = ''
  clientFilters.ip = ''
  applyFilter()
}

onMounted(() => {
  loadLogs()
})

async function loadLogs() {
  loading.value = true
  expandedIds.value.clear()
  try {
    const result = await auditApi.list({
      user_email: filterEmail.value || undefined,
      action: filterAction.value || undefined,
      resource_type: filterResourceType.value || undefined,
      date_from: filterDateFrom.value || undefined,
      date_to: filterDateTo.value || undefined,
      page: currentPage.value,
      per_page: PER_PAGE,
    })
    logs.value = result.logs
    total.value = result.total
    currentPage.value = result.page
    totalPages.value = result.pages
  } catch {
    toast.error('Impossible de charger le journal d\'audit')
  } finally {
    loading.value = false
  }
}

function applyFilter() {
  currentPage.value = 1
  loadLogs()
}

function goToPage(page: number) {
  currentPage.value = page
  loadLogs()
}

function toggleExpanded(id: number) {
  if (expandedIds.value.has(id)) {
    expandedIds.value.delete(id)
  } else {
    expandedIds.value.add(id)
  }
}

function statusBadgeClass(status: number): string {
  if (status >= 200 && status < 300) {
    return 'bg-success-100 text-success-700 dark:bg-success-500/20 dark:text-success-400'
  }
  if (status >= 400 && status < 500) {
    return 'bg-warning-100 text-warning-700 dark:bg-warning-500/20 dark:text-warning-400'
  }
  if (status >= 500) {
    return 'bg-error-100 text-error-700 dark:bg-error-500/20 dark:text-error-400'
  }
  return 'bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300'
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('fr-FR', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function formatJson(raw: string): string {
  try {
    return JSON.stringify(JSON.parse(raw), null, 2)
  } catch {
    return raw
  }
}
</script>
