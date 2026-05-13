<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import * as apiCatalog from '@/api/apiCatalog'
import type { ApiCatalogEndpoint, ApiCatalogService, Protocol } from '@/types/apiCatalog'
import { useAuthStore } from '@/stores/auth'
import ProtocolBadge from '@/components/api-catalog/ProtocolBadge.vue'
import ScanStatusBadge from '@/components/api-catalog/ScanStatusBadge.vue'
import EndpointTable from '@/components/api-catalog/EndpointTable.vue'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const service = ref<ApiCatalogService | null>(null)
const endpoints = ref<ApiCatalogEndpoint[]>([])
const loading = ref(true)
const error = ref('')
const rescanning = ref(false)
const rescanMsg = ref('')
const activeTab = ref<Protocol>('rest')

const id = computed(() => String(route.params.id))

async function load() {
  loading.value = true
  error.value = ''
  try {
    const r = await apiCatalog.get(id.value)
    service.value = r.service
    endpoints.value = r.endpoints
    // Select first available protocol tab
    const protocols: Protocol[] = ['rest', 'ws', 'grpc']
    const available = protocols.filter((p) => r.endpoints.some((e) => e.protocol === p))
    if (available.length) activeTab.value = available[0]
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Erreur de chargement'
  } finally {
    loading.value = false
  }
}

onMounted(load)

const availableProtocols = computed<Protocol[]>(() => {
  const all: Protocol[] = ['rest', 'ws', 'grpc']
  return all.filter((p) => endpoints.value.some((e) => e.protocol === p))
})

const tabEndpoints = computed(() =>
  endpoints.value.filter((e) => e.protocol === activeTab.value),
)

const protocolLabel: Record<Protocol, string> = { rest: 'REST', ws: 'WS', grpc: 'gRPC' }

const statusLabel = { active: 'Actif', deprecated: 'Déprécié', down: 'Hors ligne' }
const statusCls = { active: 'text-green-600', deprecated: 'text-yellow-600', down: 'text-red-600' }

async function rescanOne() {
  rescanning.value = true
  rescanMsg.value = ''
  try {
    const r = await apiCatalog.rescanOne(id.value)
    rescanMsg.value = `Rescan : ${r.servicesOk}/${r.servicesScanned} OK`
    await load()
  } catch (e) {
    rescanMsg.value = e instanceof Error ? e.message : 'Erreur rescan'
  } finally {
    rescanning.value = false
  }
}

async function deleteService() {
  if (!confirm(`Supprimer "${service.value?.name}" ? Cette action est irréversible.`)) return
  try {
    await apiCatalog.remove(id.value)
    router.push('/admin/api')
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Erreur de suppression'
  }
}
</script>

<template>
  <div class="p-6">
    <div class="mb-4 flex items-center gap-4">
      <button
        type="button"
        class="inline-flex items-center gap-1.5 text-sm text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white"
        @click="router.push('/admin/api')"
      >
        ← Retour
      </button>
      <h1 class="text-2xl font-bold text-gray-900 dark:text-white">
        {{ service?.name ?? 'Détail API' }}
      </h1>
    </div>

    <div v-if="error" class="mb-4 p-3 bg-red-50 text-red-700 rounded-md">{{ error }}</div>
    <div v-if="rescanMsg" class="mb-3 p-3 bg-blue-50 text-blue-700 rounded-md text-sm">{{ rescanMsg }}</div>

    <div v-if="loading" class="flex items-center justify-center py-20">
      <span class="text-2xl text-gray-400">⏳</span>
    </div>

    <template v-else-if="service">
      <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <!-- Main content -->
        <div class="lg:col-span-2 space-y-6">
          <!-- Header info -->
          <div class="bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-800 p-5">
            <div class="flex flex-wrap items-center gap-3 mb-3">
              <div class="flex gap-1">
                <ProtocolBadge v-for="p in service.protocols" :key="p" :protocol="p" />
              </div>
              <span :class="statusCls[service.status]" class="text-sm font-medium">
                {{ statusLabel[service.status] }}
              </span>
              <ScanStatusBadge :ok="service.lastScanOk" :at="service.lastScannedAt" />
            </div>
            <p class="font-mono text-sm text-gray-600 dark:text-gray-300 break-all">
              {{ service.baseUrl }}
            </p>
            <p v-if="service.description" class="mt-2 text-sm text-gray-700 dark:text-gray-300">
              {{ service.description }}
            </p>
          </div>

          <!-- Endpoints tabs -->
          <div class="bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-800">
            <div class="flex border-b border-gray-200 dark:border-gray-800 px-4">
              <button
                v-for="p in availableProtocols"
                :key="p"
                type="button"
                :class="[
                  'px-4 py-3 text-sm font-medium border-b-2 -mb-px transition-colors',
                  activeTab === p
                    ? 'border-blue-500 text-blue-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700 dark:hover:text-gray-300',
                ]"
                @click="activeTab = p"
              >
                {{ protocolLabel[p] }}
              </button>
              <p
                v-if="!availableProtocols.length"
                class="px-4 py-3 text-sm text-gray-400"
              >
                Aucun endpoint scanné
              </p>
            </div>
            <div class="p-4">
              <EndpointTable :endpoints="tabEndpoints" />
            </div>
          </div>
        </div>

        <!-- Side panel: metadata + admin actions -->
        <div class="space-y-4">
          <div class="bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-800 p-5">
            <h2 class="text-sm font-semibold text-gray-900 dark:text-white mb-3">Métadonnées</h2>
            <dl class="space-y-2 text-sm">
              <div v-if="service.owner">
                <dt class="text-gray-500">Propriétaire</dt>
                <dd class="font-medium">{{ service.owner }}</dd>
              </div>
              <div>
                <dt class="text-gray-500">Source</dt>
                <dd><code class="font-mono text-xs">{{ service.source }}</code></dd>
              </div>
              <div v-if="service.tags?.length">
                <dt class="text-gray-500">Tags</dt>
                <dd class="flex flex-wrap gap-1 mt-1">
                  <span
                    v-for="t in service.tags"
                    :key="t"
                    class="text-xs bg-gray-100 dark:bg-gray-800 px-2 py-0.5 rounded"
                  >{{ t }}</span>
                </dd>
              </div>
              <div v-if="service.apiInfoUrl">
                <dt class="text-gray-500">API Info URL</dt>
                <dd>
                  <a
                    :href="service.apiInfoUrl"
                    target="_blank"
                    rel="noopener noreferrer"
                    class="text-blue-600 hover:underline font-mono text-xs break-all"
                  >{{ service.apiInfoUrl }}</a>
                </dd>
              </div>
              <div v-if="service.grpcAddress">
                <dt class="text-gray-500">Adresse gRPC</dt>
                <dd><code class="font-mono text-xs">{{ service.grpcAddress }}</code></dd>
              </div>
              <div>
                <dt class="text-gray-500">Créé le</dt>
                <dd>{{ new Date(service.createdAt).toLocaleDateString('fr-FR') }}</dd>
              </div>
              <div>
                <dt class="text-gray-500">Mis à jour le</dt>
                <dd>{{ new Date(service.updatedAt).toLocaleDateString('fr-FR') }}</dd>
              </div>
            </dl>
          </div>

          <!-- Actions: Modifier/Rescan open to all auth users; Supprimer admin-only -->
          <div class="bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-800 p-5 space-y-2">
            <h2 class="text-sm font-semibold text-gray-900 dark:text-white mb-3">Actions</h2>
            <button
              type="button"
              class="w-full px-4 py-2 text-sm rounded-md border border-gray-300 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-800"
              @click="router.push(`/admin/api/${id}/edit`)"
            >
              Modifier
            </button>
            <button
              type="button"
              class="w-full px-4 py-2 text-sm rounded-md border border-gray-300 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-800 disabled:opacity-50"
              :disabled="rescanning"
              @click="rescanOne"
            >
              {{ rescanning ? 'Scan en cours…' : 'Rescan' }}
            </button>
            <button
              v-if="auth.isAdmin"
              type="button"
              class="w-full px-4 py-2 text-sm rounded-md border border-red-300 text-red-600 hover:bg-red-50 dark:border-red-800 dark:hover:bg-red-900/20"
              @click="deleteService"
            >
              Supprimer
            </button>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>
