<template>
  <div>
    <PageBreadcrumb page-title="Tableau de bord" />

    <!-- Loading -->
    <div v-if="isLoading" class="text-center py-12">
      <i class="pi pi-spinner pi-spin text-2xl text-brand-500" />
    </div>

    <!-- Dashboard content -->
    <div v-else class="flex flex-col lg:flex-row gap-6">
      <!-- Main area -->
      <div class="flex-1 min-w-0 space-y-6">
        <!-- KPI Cards -->
        <div class="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <div
            v-for="kpi in kpiCards"
            :key="kpi.label"
            class="rounded-lg border border-gray-200 bg-white p-5 dark:border-gray-800 dark:bg-gray-900"
          >
            <div class="flex items-center gap-3 mb-3">
              <div
                :class="[
                  'flex h-10 w-10 items-center justify-center rounded-lg',
                  kpi.bgClass,
                ]"
              >
                <i :class="[kpi.icon, 'text-lg', kpi.iconClass]" />
              </div>
            </div>
            <div class="text-2xl font-bold text-gray-900 dark:text-white">
              {{ kpi.value }}
            </div>
            <div class="text-sm text-gray-500 dark:text-gray-400 mt-0.5">
              {{ kpi.label }}
            </div>
            <div class="text-xs text-gray-400 dark:text-gray-500 mt-1">
              {{ kpi.subtext }}
            </div>
          </div>
        </div>

        <!-- Server Health Donut -->
        <div class="rounded-lg border border-gray-200 bg-white p-5 dark:border-gray-800 dark:bg-gray-900">
          <h3 class="text-sm font-medium text-gray-700 dark:text-gray-300 mb-4">
            Santé des serveurs
          </h3>
          <div class="flex items-center gap-8">
            <svg viewBox="0 0 36 36" class="w-28 h-28 flex-shrink-0">
              <!-- Background circle -->
              <circle
                cx="18" cy="18" r="15.915"
                fill="none" stroke="#e5e7eb" stroke-width="3"
                class="dark:stroke-gray-700"
              />
              <!-- Healthy arc -->
              <circle
                cx="18" cy="18" r="15.915"
                fill="none" stroke="#34d399" stroke-width="3"
                stroke-linecap="round"
                :stroke-dasharray="`${healthyPct} ${100 - healthyPct}`"
                stroke-dashoffset="25"
              />
              <!-- Unhealthy arc -->
              <circle
                v-if="unhealthyPct > 0"
                cx="18" cy="18" r="15.915"
                fill="none" stroke="#ef4444" stroke-width="3"
                stroke-linecap="round"
                :stroke-dasharray="`${unhealthyPct} ${100 - unhealthyPct}`"
                :stroke-dashoffset="25 - healthyPct"
              />
              <!-- Center text -->
              <text x="18" y="18.5" text-anchor="middle" dominant-baseline="middle"
                class="fill-gray-900 dark:fill-white text-[0.5rem] font-bold"
              >
                {{ healthyPct }}%
              </text>
            </svg>
            <div class="flex flex-col gap-2 text-sm">
              <div class="flex items-center gap-2">
                <span class="w-3 h-3 rounded-full bg-emerald-400" />
                <span class="text-gray-600 dark:text-gray-400">Healthy — {{ healthyCnt }}</span>
              </div>
              <div class="flex items-center gap-2">
                <span class="w-3 h-3 rounded-full bg-red-500" />
                <span class="text-gray-600 dark:text-gray-400">Unhealthy — {{ unhealthyCnt }}</span>
              </div>
              <div class="flex items-center gap-2">
                <span class="w-3 h-3 rounded-full bg-gray-400" />
                <span class="text-gray-600 dark:text-gray-400">Unknown — {{ unknownCnt }}</span>
              </div>
            </div>
          </div>
        </div>

        <!-- Server Status Table -->
        <div class="rounded-lg border border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-900">
          <div class="px-5 py-4 border-b border-gray-200 dark:border-gray-800">
            <h3 class="text-sm font-medium text-gray-700 dark:text-gray-300">
              Statut des serveurs
            </h3>
          </div>
          <div class="overflow-x-auto">
            <table class="w-full text-sm">
              <thead>
                <tr class="border-b border-gray-200 dark:border-gray-800">
                  <th class="px-5 py-3 text-left font-medium text-gray-500 dark:text-gray-400">Nom</th>
                  <th class="px-5 py-3 text-left font-medium text-gray-500 dark:text-gray-400">Santé</th>
                  <th class="px-5 py-3 text-left font-medium text-gray-500 dark:text-gray-400">Tools</th>
                  <th class="px-5 py-3 text-left font-medium text-gray-500 dark:text-gray-400">Resources</th>
                  <th class="px-5 py-3 text-left font-medium text-gray-500 dark:text-gray-400">Dernier check</th>
                  <th class="px-5 py-3 text-left font-medium text-gray-500 dark:text-gray-400">Tags</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="server in sortedServers"
                  :key="server.id"
                  class="border-b border-gray-100 dark:border-gray-800 last:border-0"
                >
                  <td class="px-5 py-3 font-medium text-gray-900 dark:text-white">
                    {{ server.name }}
                  </td>
                  <td class="px-5 py-3">
                    <span
                      :class="[
                        'inline-flex items-center gap-1.5 text-xs font-medium px-2 py-0.5 rounded-full',
                        healthBadgeClass(server.health_status),
                      ]"
                    >
                      <span
                        :class="[
                          'w-1.5 h-1.5 rounded-full',
                          healthDotClass(server.health_status),
                        ]"
                      />
                      {{ server.health_status }}
                    </span>
                  </td>
                  <td class="px-5 py-3 text-gray-600 dark:text-gray-400">
                    {{ server.tools_count }}
                  </td>
                  <td class="px-5 py-3 text-gray-600 dark:text-gray-400">
                    {{ server.resources_count }}
                  </td>
                  <td class="px-5 py-3 text-gray-500 dark:text-gray-400 text-xs">
                    {{ formatRelativeTime(server.last_health_check) }}
                  </td>
                  <td class="px-5 py-3">
                    <div class="flex flex-wrap gap-1">
                      <span
                        v-for="tag in server.tags"
                        :key="tag"
                        class="text-xs bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400 px-2 py-0.5 rounded"
                      >
                        {{ tag }}
                      </span>
                    </div>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <div v-if="servers.length > 10" class="px-5 py-3 border-t border-gray-200 dark:border-gray-800">
            <router-link
              to="/servers"
              class="text-sm text-brand-500 hover:text-brand-600"
            >
              Voir tous les serveurs →
            </router-link>
          </div>
        </div>
      </div>

      <!-- Sidebar -->
      <div class="w-full lg:w-80 flex-shrink-0 space-y-6">
        <!-- Quick Stats -->
        <div class="rounded-lg border border-gray-200 bg-white p-5 dark:border-gray-800 dark:bg-gray-900">
          <h3 class="text-sm font-medium text-gray-700 dark:text-gray-300 mb-4">
            Statistiques rapides
          </h3>
          <div class="space-y-3 text-sm">
            <div class="flex justify-between text-gray-600 dark:text-gray-400">
              <span>Utilisateurs</span>
              <span class="font-medium text-gray-900 dark:text-white">{{ users.length }}</span>
            </div>
            <div class="flex justify-between text-gray-600 dark:text-gray-400">
              <span class="ml-3">Admin</span>
              <span>{{ usersByRole.admin }}</span>
            </div>
            <div class="flex justify-between text-gray-600 dark:text-gray-400">
              <span class="ml-3">Lecture seule</span>
              <span>{{ usersByRole['read-only'] }}</span>
            </div>
            <div class="flex justify-between text-gray-600 dark:text-gray-400">
              <span class="ml-3">Config only</span>
              <span>{{ usersByRole['config-only'] }}</span>
            </div>
            <hr class="border-gray-200 dark:border-gray-700" />
            <div class="flex justify-between text-gray-600 dark:text-gray-400">
              <span>Serveurs healthy</span>
              <span class="font-medium text-emerald-500">{{ healthyCnt }}</span>
            </div>
            <div class="flex justify-between text-gray-600 dark:text-gray-400">
              <span>Serveurs unhealthy</span>
              <span class="font-medium text-red-500">{{ unhealthyCnt }}</span>
            </div>
            <div class="flex justify-between text-gray-600 dark:text-gray-400">
              <span>Serveurs unknown</span>
              <span class="font-medium text-gray-400">{{ unknownCnt }}</span>
            </div>
          </div>
        </div>

        <!-- Recent Activity -->
        <div class="rounded-lg border border-gray-200 bg-white p-5 dark:border-gray-800 dark:bg-gray-900">
          <h3 class="text-sm font-medium text-gray-700 dark:text-gray-300 mb-4">
            Activité récente
          </h3>
          <div v-if="auditLogs.length" class="space-y-3">
            <div
              v-for="log in auditLogs"
              :key="log.id"
              class="flex items-start gap-3"
            >
              <div
                :class="[
                  'mt-0.5 flex h-7 w-7 items-center justify-center rounded-full flex-shrink-0',
                  actionBgClass(log.action),
                ]"
              >
                <i :class="[actionIcon(log.action), 'text-xs', actionIconClass(log.action)]" />
              </div>
              <div class="min-w-0 flex-1">
                <p class="text-sm text-gray-700 dark:text-gray-300 truncate">
                  <span class="font-medium">{{ log.user_email.split('@')[0] }}</span>
                  {{ actionLabel(log.action) }}
                  <span class="text-gray-500 dark:text-gray-400">{{ log.resource_type }}</span>
                </p>
                <p class="text-xs text-gray-400 dark:text-gray-500">
                  {{ formatRelativeTime(log.created_at) }}
                </p>
              </div>
            </div>
          </div>
          <p v-else class="text-sm text-gray-400 dark:text-gray-500">
            Aucune activité récente
          </p>
          <router-link
            to="/audit-logs"
            class="block mt-4 text-sm text-brand-500 hover:text-brand-600"
          >
            Voir le journal complet →
          </router-link>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { serversApi } from '@/api/servers'
import { tokensApi } from '@/api/tokens'
import { oauth2Api } from '@/api/oauth2'
import { usersApi } from '@/api/users'
import { auditApi } from '@/api/audit'
import PageBreadcrumb from '@/components/common/PageBreadcrumb.vue'
import type { Server } from '@/types/server'
import type { ScopeToken } from '@/types/token'
import type { OAuth2Client } from '@/types/oauth2'
import type { User } from '@/types/user'
import type { AuditLog } from '@/types/audit'

const isLoading = ref(true)
const servers = ref<Server[]>([])
const tokens = ref<ScopeToken[]>([])
const clients = ref<OAuth2Client[]>([])
const users = ref<User[]>([])
const auditLogs = ref<AuditLog[]>([])
const totalTools = ref(0)

onMounted(async () => {
  try {
    const [serversRes, toolsRes, tokensRes, clientsRes, usersRes, auditRes] = await Promise.all([
      serversApi.list(),
      serversApi.listTools(),
      tokensApi.list(),
      oauth2Api.list(),
      usersApi.list(),
      auditApi.list({ per_page: 10 }),
    ])
    servers.value = serversRes.servers
    totalTools.value = Array.isArray(toolsRes) ? toolsRes.length : 0
    tokens.value = tokensRes.tokens
    clients.value = clientsRes.clients
    users.value = usersRes.users
    auditLogs.value = auditRes.logs
  } catch (err) {
    console.error('[dashboard] failed to load data:', err)
  } finally {
    isLoading.value = false
  }
})

// --- KPI computations ---
const activeTokens = computed(() => tokens.value.filter(t => t.is_active))
const revokedTokens = computed(() => tokens.value.filter(t => !t.is_active))
const activeClients = computed(() => clients.value.filter(c => c.is_active))
const revokedClients = computed(() => clients.value.filter(c => !c.is_active))

const healthyCnt = computed(() => servers.value.filter(s => s.health_status === 'healthy').length)
const unhealthyCnt = computed(() => servers.value.filter(s => s.health_status === 'unhealthy').length)
const unknownCnt = computed(() => servers.value.filter(s => s.health_status !== 'healthy' && s.health_status !== 'unhealthy').length)

const healthyPct = computed(() => {
  if (servers.value.length === 0) return 0
  return Math.round((healthyCnt.value / servers.value.length) * 100)
})
const unhealthyPct = computed(() => {
  if (servers.value.length === 0) return 0
  return Math.round((unhealthyCnt.value / servers.value.length) * 100)
})

const kpiCards = computed(() => [
  {
    label: 'Serveurs',
    value: servers.value.length,
    subtext: `${healthyCnt.value} healthy / ${unhealthyCnt.value} unhealthy`,
    icon: 'pi pi-server',
    bgClass: 'bg-blue-50 dark:bg-blue-500/10',
    iconClass: 'text-blue-500',
  },
  {
    label: 'Tools',
    value: totalTools.value,
    subtext: `sur ${servers.value.filter(s => s.is_active).length} serveurs actifs`,
    icon: 'pi pi-wrench',
    bgClass: 'bg-purple-50 dark:bg-purple-500/10',
    iconClass: 'text-purple-500',
  },
  {
    label: 'Tokens',
    value: activeTokens.value.length,
    subtext: `${revokedTokens.value.length} révoqués`,
    icon: 'pi pi-key',
    bgClass: 'bg-amber-50 dark:bg-amber-500/10',
    iconClass: 'text-amber-500',
  },
  {
    label: 'Clients OAuth2',
    value: activeClients.value.length,
    subtext: `${revokedClients.value.length} révoqués`,
    icon: 'pi pi-shield',
    bgClass: 'bg-pink-50 dark:bg-pink-500/10',
    iconClass: 'text-pink-500',
  },
])

// --- Server table ---
const sortedServers = computed(() => {
  const sorted = [...servers.value].sort((a, b) => {
    const order: Record<string, number> = { unhealthy: 0, unknown: 1, healthy: 2 }
    const aOrder = order[a.health_status] ?? 1
    const bOrder = order[b.health_status] ?? 1
    if (aOrder !== bOrder) return aOrder - bOrder
    return a.name.localeCompare(b.name)
  })
  return sorted.slice(0, 10)
})

function healthBadgeClass(status: string): string {
  if (status === 'healthy') return 'bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-400'
  if (status === 'unhealthy') return 'bg-red-50 text-red-700 dark:bg-red-500/10 dark:text-red-400'
  return 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-400'
}

function healthDotClass(status: string): string {
  if (status === 'healthy') return 'bg-emerald-500'
  if (status === 'unhealthy') return 'bg-red-500'
  return 'bg-gray-400'
}

// --- User stats ---
const usersByRole = computed(() => {
  const counts: Record<string, number> = { admin: 0, 'read-only': 0, 'config-only': 0 }
  users.value.forEach(u => {
    const role = u.role
    if (role in counts) counts[role]!++
  })
  return counts
})

// --- Audit feed helpers ---
function actionIcon(action: string): string {
  const icons: Record<string, string> = {
    CREATE: 'pi pi-plus',
    UPDATE: 'pi pi-pencil',
    DELETE: 'pi pi-trash',
    ENABLE: 'pi pi-check',
    DISABLE: 'pi pi-times',
    DISCOVER: 'pi pi-refresh',
    REVOKE: 'pi pi-ban',
  }
  return icons[action] || 'pi pi-circle'
}

function actionBgClass(action: string): string {
  const classes: Record<string, string> = {
    CREATE: 'bg-emerald-50 dark:bg-emerald-500/10',
    UPDATE: 'bg-blue-50 dark:bg-blue-500/10',
    DELETE: 'bg-red-50 dark:bg-red-500/10',
    ENABLE: 'bg-emerald-50 dark:bg-emerald-500/10',
    DISABLE: 'bg-amber-50 dark:bg-amber-500/10',
    DISCOVER: 'bg-purple-50 dark:bg-purple-500/10',
    REVOKE: 'bg-red-50 dark:bg-red-500/10',
  }
  return classes[action] || 'bg-gray-100 dark:bg-gray-700'
}

function actionIconClass(action: string): string {
  const classes: Record<string, string> = {
    CREATE: 'text-emerald-500',
    UPDATE: 'text-blue-500',
    DELETE: 'text-red-500',
    ENABLE: 'text-emerald-500',
    DISABLE: 'text-amber-500',
    DISCOVER: 'text-purple-500',
    REVOKE: 'text-red-500',
  }
  return classes[action] || 'text-gray-500'
}

function actionLabel(action: string): string {
  const labels: Record<string, string> = {
    CREATE: ' a créé ',
    UPDATE: ' a modifié ',
    DELETE: ' a supprimé ',
    ENABLE: ' a activé ',
    DISABLE: ' a désactivé ',
    DISCOVER: ' a découvert ',
    REVOKE: ' a révoqué ',
  }
  return labels[action] || ` ${action.toLowerCase()} `
}

function formatRelativeTime(dateStr?: string): string {
  if (!dateStr) return '—'
  const now = Date.now()
  const then = new Date(dateStr).getTime()
  const diffMs = now - then
  const diffMin = Math.floor(diffMs / 60000)
  if (diffMin < 1) return "à l'instant"
  if (diffMin < 60) return `il y a ${diffMin} min`
  const diffHours = Math.floor(diffMin / 60)
  if (diffHours < 24) return `il y a ${diffHours}h`
  const diffDays = Math.floor(diffHours / 24)
  return `il y a ${diffDays}j`
}
</script>
