<template>
  <div class="space-y-3">
    <!-- Mode select -->
    <div>
      <label for="ringover-filter-mode" class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
        Restriction des appels Ringover
      </label>
      <select
        id="ringover-filter-mode"
        :value="model.mode"
        class="h-11 w-full rounded-lg border border-gray-300 bg-transparent px-4 py-2.5 text-sm text-gray-800 shadow-theme-xs focus:border-brand-300 focus:outline-hidden focus:ring-3 focus:ring-brand-500/10 dark:border-gray-700 dark:bg-gray-900 dark:text-white/90 appearance-none"
        @change="onModeChange(($event.target as HTMLSelectElement).value as RingoverFilterMode)"
      >
        <option value="none">Aucune restriction (acc&egrave;s complet)</option>
        <option value="users">Utilisateurs s&eacute;lectionn&eacute;s</option>
        <option value="teams">&Eacute;quipes s&eacute;lectionn&eacute;es</option>
        <option value="creator">Cr&eacute;ateur du jeton uniquement</option>
      </select>
      <p class="text-xs text-gray-400 dark:text-gray-500 mt-1">
        Limite les appels Ringover accessibles par ce jeton selon l'agent propri&eacute;taire (<code>user_id</code>) de chaque appel.
      </p>
    </div>

    <!-- Loading / disabled banner -->
    <div v-if="loading" class="flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400">
      <i class="pi pi-spinner pi-spin" /> Chargement des utilisateurs Ringover&hellip;
    </div>
    <div
      v-else-if="loadError"
      class="rounded-md border border-warning-300 dark:border-warning-500/30 bg-warning-50 dark:bg-warning-500/15 p-3 text-sm text-warning-800 dark:text-warning-400"
    >
      <i class="pi pi-exclamation-triangle mr-1" />
      {{ loadError }}
    </div>

    <!-- Users picker -->
    <div v-if="model.mode === 'users' && !loading && !loadError">
      <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
        Utilisateurs autoris&eacute;s
      </label>
      <div
        class="max-h-56 overflow-y-auto rounded-lg border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-900 divide-y divide-gray-100 dark:divide-gray-800"
      >
        <label
          v-for="u in users"
          :key="u.user_id"
          class="flex items-center gap-2 px-3 py-2 text-sm text-gray-700 dark:text-gray-300 cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800/50"
        >
          <input
            type="checkbox"
            class="rounded border-gray-300 text-brand-500 dark:border-gray-700"
            :checked="(model.user_ids || []).includes(u.user_id)"
            @change="toggleUser(u.user_id, ($event.target as HTMLInputElement).checked)"
          />
          <span class="flex-1">{{ formatUser(u) }}</span>
        </label>
        <div v-if="users.length === 0" class="px-3 py-2 text-sm text-gray-400 dark:text-gray-500">
          Aucun utilisateur Ringover trouv&eacute;.
        </div>
      </div>
      <p class="text-xs text-gray-400 dark:text-gray-500 mt-1">
        S&eacute;lectionnez un ou plusieurs utilisateurs. Si la liste est vide, le jeton ne pourra acc&eacute;der &agrave; aucun appel.
      </p>
    </div>

    <!-- Teams picker -->
    <div v-if="model.mode === 'teams' && !loading && !loadError">
      <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
        &Eacute;quipes autoris&eacute;es
      </label>
      <div
        class="max-h-56 overflow-y-auto rounded-lg border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-900 divide-y divide-gray-100 dark:divide-gray-800"
      >
        <label
          v-for="t in teams"
          :key="t.id"
          class="flex items-center gap-2 px-3 py-2 text-sm text-gray-700 dark:text-gray-300 cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800/50"
        >
          <input
            type="checkbox"
            class="rounded border-gray-300 text-brand-500 dark:border-gray-700"
            :checked="(model.team_ids || []).includes(t.id)"
            @change="toggleTeam(t.id, ($event.target as HTMLInputElement).checked)"
          />
          <span class="flex-1">{{ t.name || `#${t.id}` }}</span>
        </label>
        <div v-if="teams.length === 0" class="px-3 py-2 text-sm text-gray-400 dark:text-gray-500">
          Aucune &eacute;quipe Ringover d&eacute;tect&eacute;e dans votre espace de travail.
        </div>
      </div>
      <p class="text-xs text-gray-400 dark:text-gray-500 mt-1">
        Les nouveaux membres ajout&eacute;s aux &eacute;quipes choisies h&eacute;riteront automatiquement de l'acc&egrave;s.
      </p>
    </div>

    <!-- Creator info -->
    <div
      v-if="model.mode === 'creator'"
      class="rounded-md border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900/40 p-3 text-sm text-gray-600 dark:text-gray-400"
    >
      <i class="pi pi-info-circle mr-1" />
      L'identifiant Ringover du cr&eacute;ateur du jeton sera r&eacute;solu &agrave; partir de son adresse email lors de la cr&eacute;ation, puis utilis&eacute; comme filtre <code>advanced.users</code>.
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted, computed } from 'vue'
import { ringoverApi } from '@/api/ringover'
import type { RingoverFilter, RingoverFilterMode, RingoverUser, RingoverTeam } from '@/types/ringover'

const props = defineProps<{ modelValue: RingoverFilter }>()
const emit = defineEmits<{ (e: 'update:modelValue', value: RingoverFilter): void }>()

const model = computed<RingoverFilter>(() => props.modelValue)

const users = ref<RingoverUser[]>([])
const teams = ref<RingoverTeam[]>([])
const loading = ref(false)
const loadError = ref<string | null>(null)
let loaded = false

async function ensureLoaded() {
  if (loaded || loading.value) return
  loading.value = true
  loadError.value = null
  try {
    const [u, t] = await Promise.all([ringoverApi.listUsers(), ringoverApi.listTeams()])
    users.value = u.users || []
    teams.value = t.teams || []
    loaded = true
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err)
    if (message.includes('not configured') || message.includes('503')) {
      loadError.value =
        "L'intégration Ringover n'est pas configurée côté gateway (RINGOVER_INTERNAL_URL / RINGOVER_ADMIN_TOKEN)."
    } else {
      loadError.value = `Impossible de charger les utilisateurs Ringover : ${message}`
    }
  } finally {
    loading.value = false
  }
}

function onModeChange(mode: RingoverFilterMode) {
  const next: RingoverFilter = { mode }
  if (mode === 'users') next.user_ids = []
  if (mode === 'teams') next.team_ids = []
  emit('update:modelValue', next)
  if (mode === 'users' || mode === 'teams') {
    ensureLoaded()
  }
}

function toggleUser(id: number, checked: boolean) {
  const current = new Set(model.value.user_ids || [])
  if (checked) current.add(id)
  else current.delete(id)
  emit('update:modelValue', { ...model.value, user_ids: Array.from(current) })
}

function toggleTeam(id: number, checked: boolean) {
  const current = new Set(model.value.team_ids || [])
  if (checked) current.add(id)
  else current.delete(id)
  emit('update:modelValue', { ...model.value, team_ids: Array.from(current) })
}

function formatUser(u: RingoverUser): string {
  const name = [u.firstname, u.lastname].filter(Boolean).join(' ').trim()
  const head = name && u.email ? `${name} - ${u.email}` : name || u.email || `#${u.user_id}`
  return u.team_name ? `${head} · ${u.team_name}` : head
}

watch(
  () => model.value.mode,
  (m) => {
    if (m === 'users' || m === 'teams') {
      ensureLoaded()
    }
  }
)

onMounted(() => {
  if (model.value.mode === 'users' || model.value.mode === 'teams') {
    ensureLoaded()
  }
})
</script>
