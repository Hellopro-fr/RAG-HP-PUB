<template>
  <div class="space-y-3">
    <!-- Mode select -->
    <div>
      <label for="leexi-filter-mode" class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
        Restriction des appels Leexi
      </label>
      <select
        id="leexi-filter-mode"
        :value="model.mode"
        class="h-11 w-full rounded-lg border border-gray-300 bg-transparent px-4 py-2.5 text-sm text-gray-800 shadow-theme-xs focus:border-brand-300 focus:outline-hidden focus:ring-3 focus:ring-brand-500/10 dark:border-gray-700 dark:bg-gray-900 dark:text-white/90 appearance-none"
        @change="onModeChange(($event.target as HTMLSelectElement).value as LeexiFilterMode)"
      >
        <option value="none">Aucune restriction (acc&egrave;s complet)</option>
        <option value="users">Utilisateurs s&eacute;lectionn&eacute;s</option>
        <option value="teams">&Eacute;quipes s&eacute;lectionn&eacute;es</option>
        <option value="creator">Cr&eacute;ateur du jeton uniquement</option>
      </select>
      <p class="text-xs text-gray-400 dark:text-gray-500 mt-1">
        Limite les appels Leexi accessibles par ce jeton selon le propri&eacute;taire (<code>owner_uuid</code>) des appels.
      </p>
    </div>

    <!-- Loading / disabled banner -->
    <div v-if="loading" class="flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400">
      <i class="pi pi-spinner pi-spin" /> Chargement des utilisateurs Leexi&hellip;
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
          :key="u.uuid"
          class="flex items-center gap-2 px-3 py-2 text-sm text-gray-700 dark:text-gray-300 cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800/50"
        >
          <input
            type="checkbox"
            class="rounded border-gray-300 text-brand-500 dark:border-gray-700"
            :checked="(model.user_uuids || []).includes(u.uuid)"
            @change="toggleUser(u.uuid, ($event.target as HTMLInputElement).checked)"
          />
          <span class="flex-1">{{ formatUser(u) }}</span>
        </label>
        <div v-if="users.length === 0" class="px-3 py-2 text-sm text-gray-400 dark:text-gray-500">
          Aucun utilisateur Leexi trouv&eacute;.
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
          :key="t.uuid"
          class="flex items-center gap-2 px-3 py-2 text-sm text-gray-700 dark:text-gray-300 cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800/50"
        >
          <input
            type="checkbox"
            class="rounded border-gray-300 text-brand-500 dark:border-gray-700"
            :checked="(model.team_uuids || []).includes(t.uuid)"
            @change="toggleTeam(t.uuid, ($event.target as HTMLInputElement).checked)"
          />
          <span class="flex-1">{{ t.name || t.uuid }}</span>
        </label>
        <div v-if="teams.length === 0" class="px-3 py-2 text-sm text-gray-400 dark:text-gray-500">
          Aucune &eacute;quipe Leexi d&eacute;tect&eacute;e dans votre espace de travail.
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
      L'identifiant Leexi du cr&eacute;ateur du jeton sera r&eacute;solu &agrave; partir de son adresse email lors de la cr&eacute;ation, puis utilis&eacute; comme filtre <code>owner_uuid</code>.
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted, computed } from 'vue'
import { leexiApi } from '@/api/leexi'
import type { LeexiFilter, LeexiFilterMode, LeexiUser, LeexiTeam } from '@/types/leexi'

const props = defineProps<{ modelValue: LeexiFilter }>()
const emit = defineEmits<{ (e: 'update:modelValue', value: LeexiFilter): void }>()

// Local mutable view of the v-model. Each onModeChange emits a fresh object
// so parents always see a normalised payload (no stale user_uuids when mode
// switches to 'teams', etc.).
const model = computed<LeexiFilter>(() => props.modelValue)

const users = ref<LeexiUser[]>([])
const teams = ref<LeexiTeam[]>([])
const loading = ref(false)
const loadError = ref<string | null>(null)
let loaded = false

async function ensureLoaded() {
  if (loaded || loading.value) return
  loading.value = true
  loadError.value = null
  try {
    const [u, t] = await Promise.all([leexiApi.listUsers(), leexiApi.listTeams()])
    users.value = u.users || []
    teams.value = t.teams || []
    loaded = true
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err)
    if (message.includes('not configured') || message.includes('503')) {
      loadError.value =
        "L'int\u00e9gration Leexi n'est pas configur\u00e9e c\u00f4t\u00e9 gateway (LEEXI_INTERNAL_URL / LEEXI_ADMIN_TOKEN)."
    } else {
      loadError.value = `Impossible de charger les utilisateurs Leexi : ${message}`
    }
  } finally {
    loading.value = false
  }
}

function onModeChange(mode: LeexiFilterMode) {
  // Reset orthogonal selections to avoid persisting stale data on the server.
  const next: LeexiFilter = { mode }
  if (mode === 'users') next.user_uuids = []
  if (mode === 'teams') next.team_uuids = []
  emit('update:modelValue', next)
  if (mode === 'users' || mode === 'teams') {
    ensureLoaded()
  }
}

function toggleUser(uuid: string, checked: boolean) {
  const current = new Set(model.value.user_uuids || [])
  if (checked) current.add(uuid)
  else current.delete(uuid)
  emit('update:modelValue', { ...model.value, user_uuids: Array.from(current) })
}

function toggleTeam(uuid: string, checked: boolean) {
  const current = new Set(model.value.team_uuids || [])
  if (checked) current.add(uuid)
  else current.delete(uuid)
  emit('update:modelValue', { ...model.value, team_uuids: Array.from(current) })
}

// Format: "{First name} {Last name} - {email} · {team}" — first name is
// optional; the team segment is appended only when present. Falls back to
// email-only, then to the opaque UUID when nothing else is available.
function formatUser(u: LeexiUser): string {
  const name = [u.first_name, u.last_name].filter(Boolean).join(' ').trim()
  const head = name && u.email ? `${name} - ${u.email}` : name || u.email || u.uuid
  return u.team_name ? `${head} \u00b7 ${u.team_name}` : head
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
