<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { Plus, Trash2, UserMinus, UserPlus, Users } from 'lucide-vue-next'
import * as groupsApi from '@/api/groups'

const groups = ref<groupsApi.AdminGroup[]>([])
const selected = ref<groupsApi.AdminGroupDetail | null>(null)
const loading = ref(true)
const error = ref('')
const query = ref('')

const newName = ref('')
const newDescription = ref('')
const creating = ref(false)

const editName = ref('')
const editDescription = ref('')
const memberEmail = ref('')

const filtered = computed(() => {
  const q = query.value.trim().toLowerCase()
  if (!q) return groups.value
  return groups.value.filter(
    (g) => g.name.toLowerCase().includes(q) || g.description.toLowerCase().includes(q),
  )
})

const dirty = computed(
  () =>
    !!selected.value &&
    (editName.value.trim() !== selected.value.name ||
      editDescription.value.trim() !== selected.value.description),
)

function fail(e: unknown) {
  error.value = e instanceof Error ? e.message : 'Erreur'
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    groups.value = (await groupsApi.list()).items
  } catch (e) {
    fail(e)
  } finally {
    loading.value = false
  }
}

async function open(id: string) {
  error.value = ''
  try {
    const g = await groupsApi.get(id)
    selected.value = g
    editName.value = g.name
    editDescription.value = g.description
    memberEmail.value = ''
  } catch (e) {
    fail(e)
  }
}

async function createGroup() {
  if (!newName.value.trim()) return
  creating.value = true
  error.value = ''
  try {
    const g = await groupsApi.create(newName.value.trim(), newDescription.value.trim())
    newName.value = ''
    newDescription.value = ''
    await load()
    await open(g.id)
  } catch (e) {
    fail(e)
  } finally {
    creating.value = false
  }
}

async function saveGroup() {
  if (!selected.value || !dirty.value) return
  try {
    await groupsApi.update(selected.value.id, editName.value.trim(), editDescription.value.trim())
    await load()
    await open(selected.value.id)
  } catch (e) {
    fail(e)
  }
}

async function deleteGroup() {
  const g = selected.value
  if (!g) return
  if (!confirm(`Supprimer le groupe « ${g.name} » ? Les applications qui l'utilisent perdront les accès donnés à ce groupe.`)) return
  try {
    await groupsApi.remove(g.id)
    selected.value = null
    await load()
  } catch (e) {
    fail(e)
  }
}

async function addMember() {
  const g = selected.value
  const email = memberEmail.value.trim()
  if (!g || !email) return
  try {
    await groupsApi.addMember(g.id, email)
    await open(g.id)
    await load()
  } catch (e) {
    fail(e)
  }
}

async function removeMember(email: string) {
  const g = selected.value
  if (!g) return
  if (!confirm(`Retirer ${email} du groupe « ${g.name} » ?`)) return
  try {
    await groupsApi.removeMember(g.id, email)
    await open(g.id)
    await load()
  } catch (e) {
    fail(e)
  }
}

const inputClass =
  'h-10 w-full rounded-lg border border-gray-300 bg-transparent px-3 text-sm text-gray-800 ' +
  'focus:border-brand-300 focus:outline-none focus:ring-3 focus:ring-brand-500/10 ' +
  'dark:border-gray-700 dark:bg-gray-900 dark:text-white/90'

onMounted(load)
</script>

<template>
  <div class="p-6">
    <div class="mb-1 flex items-center justify-between">
      <h1 class="text-2xl font-semibold">Groupes</h1>
    </div>
    <p class="mb-4 text-sm text-gray-500">
      Les groupes rassemblent des utilisateurs. Les applications connectées au compte HelloPro
      (Agent Task Board…) leur attribuent ensuite des accès.
    </p>
    <div v-if="error" class="mb-4 rounded bg-red-50 p-3 text-red-700" role="alert">{{ error }}</div>

    <div class="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)]">
      <section class="rounded-2xl border border-gray-200 bg-white p-4 dark:border-gray-800 dark:bg-white/[0.03]">
        <form class="mb-4 grid gap-2" @submit.prevent="createGroup">
          <label class="text-sm font-medium" for="new-group-name">Nouveau groupe</label>
          <input id="new-group-name" v-model="newName" :class="inputClass" maxlength="120" placeholder="Nom (ex. Équipe catalogue)" />
          <input v-model="newDescription" :class="inputClass" maxlength="500" placeholder="Description (facultatif)" aria-label="Description du nouveau groupe" />
          <button
            type="submit"
            :disabled="creating || !newName.trim()"
            class="inline-flex items-center justify-center gap-2 rounded-lg bg-brand-500 px-4 py-2 text-sm text-white hover:bg-brand-600 disabled:opacity-50"
          >
            <Plus :size="16" /> Créer le groupe
          </button>
        </form>

        <input v-model="query" :class="inputClass" class="mb-3" placeholder="Rechercher un groupe…" aria-label="Rechercher un groupe" />
        <p v-if="loading" class="text-sm text-gray-500">Chargement…</p>
        <p v-else-if="filtered.length === 0" class="py-6 text-center text-sm text-gray-500">
          {{ groups.length === 0 ? 'Aucun groupe pour l’instant.' : 'Aucun groupe ne correspond.' }}
        </p>
        <ul v-else class="divide-y divide-gray-100 dark:divide-gray-800">
          <li v-for="g in filtered" :key="g.id">
            <button
              type="button"
              class="flex w-full items-center gap-3 rounded-lg px-2 py-3 text-left hover:bg-gray-50 dark:hover:bg-white/5"
              :class="selected?.id === g.id ? 'bg-brand-50 dark:bg-brand-500/10' : ''"
              @click="open(g.id)"
            >
              <span class="flex h-9 w-9 items-center justify-center rounded-full bg-gray-100 text-gray-600 dark:bg-gray-800">
                <Users :size="16" />
              </span>
              <span class="min-w-0 flex-1">
                <span class="block truncate text-sm font-medium">{{ g.name }}</span>
                <span class="block truncate text-xs text-gray-500">{{ g.description || '—' }}</span>
              </span>
              <span class="rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-600 dark:bg-gray-800">
                {{ g.member_count }} membre{{ g.member_count > 1 ? 's' : '' }}
              </span>
            </button>
          </li>
        </ul>
      </section>

      <section class="rounded-2xl border border-gray-200 bg-white p-4 dark:border-gray-800 dark:bg-white/[0.03]">
        <p v-if="!selected" class="py-12 text-center text-sm text-gray-500">
          Sélectionnez un groupe pour voir et modifier ses membres.
        </p>
        <template v-else>
          <form class="mb-6 grid gap-2" @submit.prevent="saveGroup">
            <label class="text-sm font-medium" for="edit-group-name">Nom</label>
            <input id="edit-group-name" v-model="editName" :class="inputClass" maxlength="120" />
            <label class="text-sm font-medium" for="edit-group-desc">Description</label>
            <input id="edit-group-desc" v-model="editDescription" :class="inputClass" maxlength="500" />
            <div class="mt-2 flex justify-between gap-2">
              <button
                type="button"
                class="inline-flex items-center gap-2 rounded-lg border border-red-200 px-3 py-2 text-sm text-red-600 hover:bg-red-50"
                @click="deleteGroup"
              >
                <Trash2 :size="16" /> Supprimer le groupe
              </button>
              <button
                type="submit"
                :disabled="!dirty || !editName.trim()"
                class="rounded-lg bg-brand-500 px-4 py-2 text-sm text-white hover:bg-brand-600 disabled:opacity-50"
              >
                Enregistrer
              </button>
            </div>
          </form>

          <h2 class="mb-2 text-base font-semibold">Membres ({{ selected.members.length }})</h2>
          <form class="mb-3 flex gap-2" @submit.prevent="addMember">
            <input
              v-model="memberEmail"
              :class="inputClass"
              type="email"
              placeholder="email@hellopro.fr"
              aria-label="Email du membre à ajouter"
            />
            <button
              type="submit"
              :disabled="!memberEmail.trim()"
              class="inline-flex shrink-0 items-center gap-2 rounded-lg bg-brand-500 px-3 py-2 text-sm text-white hover:bg-brand-600 disabled:opacity-50"
            >
              <UserPlus :size="16" /> Ajouter
            </button>
          </form>
          <p class="mb-3 text-xs text-gray-500">La personne doit s’être connectée une fois avec son compte HelloPro.</p>
          <p v-if="selected.members.length === 0" class="py-6 text-center text-sm text-gray-500">Aucun membre.</p>
          <ul v-else class="divide-y divide-gray-100 dark:divide-gray-800">
            <li v-for="m in selected.members" :key="m.email" class="flex items-center gap-3 py-2">
              <span class="min-w-0 flex-1">
                <span class="block truncate text-sm">{{ m.display_name || m.email }}</span>
                <span class="block truncate font-mono text-xs text-gray-500">{{ m.email }}</span>
              </span>
              <span v-if="!m.is_allowed" class="rounded-full bg-red-50 px-2 py-0.5 text-xs text-red-600">Bloqué</span>
              <button
                type="button"
                :title="`Retirer ${m.email}`"
                :aria-label="`Retirer ${m.email}`"
                class="inline-flex h-8 w-8 items-center justify-center rounded-md text-gray-500 hover:bg-gray-100 hover:text-red-600 dark:hover:bg-white/5"
                @click="removeMember(m.email)"
              >
                <UserMinus :size="16" />
              </button>
            </li>
          </ul>
        </template>
      </section>
    </div>
  </div>
</template>
