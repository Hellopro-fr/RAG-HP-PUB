<template>
  <div>
    <div class="flex items-center gap-3 mb-4">
      <button
        class="px-3 py-1.5 text-sm rounded-md text-white bg-brand-500 hover:bg-brand-600"
        @click="goToImport"
      >
        Importer depuis Sheets
      </button>
    </div>

    <div class="border-b border-gray-200 dark:border-gray-800 mb-4">
      <nav class="flex gap-4">
        <button :class="tabBtn(activeTab === 'admin')" @click="activeTab = 'admin'">
          Admin ({{ store.admin ? 1 : 0 }})
        </button>
        <button :class="tabBtn(activeTab === 'users')" @click="activeTab = 'users'">
          Utilisateurs ({{ store.usersTotal }})
        </button>
      </nav>
    </div>

    <ZohoAdminCard
      v-if="activeTab === 'admin'"
      :admin="store.admin"
      :test-result="adminTestResult"
      @create="openAdminEdit(true)"
      @edit="openAdminEdit(false)"
      @test="onTestAdmin"
      @delete="onDeleteAdmin"
    />

    <ZohoUserList
      v-else
      :rows="store.users"
      :total="store.usersTotal"
      :page="store.usersPage"
      :limit="store.usersLimit"
      :search="store.usersSearch"
      :test-results="userTestResults"
      @search="onSearchUsers"
      @page="(n) => store.fetchUsers({ page: n })"
      @edit="openUserEdit"
      @delete="onDeleteUser"
      @toggle="onToggleUser"
      @test="onTestUser"
    />

    <ZohoImportEditModal
      :open="editOpen"
      :row="editRow"
      :title="editTitle"
      @update:open="editOpen = $event"
      @submit="onEditSubmit"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useZohoImportsStore } from '@/stores/zohoImports'
import ZohoAdminCard from './ZohoAdminCard.vue'
import ZohoUserList from './ZohoUserList.vue'
import ZohoImportEditModal from './ZohoImportEditModal.vue'
import type { ZohoImportRow, ZohoImportTestResponse, ZohoImportUpdateRequest } from '@/types/zoho'

const props = defineProps<{ templateSlug: string }>()

const router = useRouter()
const store = useZohoImportsStore()

const activeTab = ref<'admin' | 'users'>('admin')
const editOpen = ref(false)
const editRow = ref<ZohoImportRow | null>(null)
const editIsCreate = ref(false)
const adminTestResult = ref<ZohoImportTestResponse | null>(null)
const userTestResults = ref<Record<string, ZohoImportTestResponse>>({})

const editTitle = computed(() => {
  if (editIsCreate.value) return 'Configurer le compte admin'
  if (editRow.value?.is_admin) return 'Modifier le compte admin'
  return "Modifier l'import"
})

onMounted(() => {
  store.fetchAdmin()
  store.fetchUsers()
})

function tabBtn(active: boolean) {
  return [
    'pb-2 -mb-px text-sm font-medium border-b-2',
    active
      ? 'border-brand-500 text-brand-500'
      : 'border-transparent text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200',
  ]
}

function goToImport() {
  router.push({
    name: 'google-sheets-import',
    query: { from: 'templates', template_slug: props.templateSlug },
  })
}

function openAdminEdit(isCreate: boolean) {
  editRow.value = store.admin
  editIsCreate.value = isCreate
  editOpen.value = true
}

function openUserEdit(r: ZohoImportRow) {
  editRow.value = r
  editIsCreate.value = false
  editOpen.value = true
}

async function onEditSubmit(patch: ZohoImportUpdateRequest) {
  if (editIsCreate.value) {
    await store.upsertAdmin({
      name: patch.name ?? 'Compte admin Zoho',
      url: patch.url ?? '',
      auth_headers: patch.auth_headers,
    })
  } else if (editRow.value) {
    await store.updateRow(editRow.value.id, patch)
  }
  editOpen.value = false
}

async function onDeleteAdmin() {
  if (!confirm('Supprimer le compte admin Zoho ?')) return
  await store.deleteAdmin()
}

async function onDeleteUser(r: ZohoImportRow) {
  if (!confirm(`Supprimer l'import de ${r.created_by} ?`)) return
  await store.deleteRow(r.id)
}

async function onToggleUser(r: ZohoImportRow) {
  await store.toggleActive(r.id, !r.is_active)
}

async function onTestAdmin() {
  if (!store.admin) return
  adminTestResult.value = await store.testRow(store.admin.id)
}

async function onTestUser(r: ZohoImportRow) {
  const res = await store.testRow(r.id)
  userTestResults.value = { ...userTestResults.value, [r.id]: res }
}

function onSearchUsers(s: string) {
  store.fetchUsers({ page: 1, search: s })
}
</script>
