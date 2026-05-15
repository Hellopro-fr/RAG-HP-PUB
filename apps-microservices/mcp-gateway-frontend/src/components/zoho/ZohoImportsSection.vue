<template>
  <div>
    <PageHeaderTabs v-model="activeTab" :tabs="tabs">
      <template #actions>
        <button
          class="px-3 py-1.5 text-sm rounded-md text-white bg-brand-500 hover:bg-brand-600"
          @click="goToAdd"
        >
          + Ajouter
        </button>
        <button
          class="px-3 py-1.5 text-sm rounded-md border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-white/5"
          @click="goToImport"
        >
          Importer depuis Sheets
        </button>
      </template>

      <ZohoAdminCard
        v-if="activeTab === 'admin'"
        :admin="store.admin"
        :test-result="adminTestResult"
        :discover-result="adminDiscoverResult"
        @create="openAdminEdit(true)"
        @edit="openAdminEdit(false)"
        @test="onTestAdmin"
        @discover="onDiscoverAdmin"
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
        :discover-results="userDiscoverResults"
        @search="onSearchUsers"
        @page="(n) => store.fetchUsers({ page: n })"
        @edit="openUserEdit"
        @delete="onDeleteUser"
        @toggle="onToggleUser"
        @test="onTestUser"
        @discover="onDiscoverUser"
      />
    </PageHeaderTabs>

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
import { useRouter, useRoute } from 'vue-router'
import { useZohoImportsStore } from '@/stores/zohoImports'
import PageHeaderTabs from '@/components/common/PageHeaderTabs.vue'
import ZohoAdminCard from './ZohoAdminCard.vue'
import ZohoUserList from './ZohoUserList.vue'
import ZohoImportEditModal from './ZohoImportEditModal.vue'
import type { ZohoImportRow, ZohoImportTestResponse, ZohoImportUpdateRequest } from '@/types/zoho'

const props = defineProps<{ templateSlug: string }>()

const router = useRouter()
const route = useRoute()
const store = useZohoImportsStore()

const activeTab = ref<'admin' | 'users'>('admin')

const tabs = computed(() => [
  { label: 'Admin', value: 'admin', count: store.admin ? 1 : 0 },
  { label: 'Utilisateurs', value: 'users', count: store.usersTotal },
])
const editOpen = ref(false)
const editRow = ref<ZohoImportRow | null>(null)
const editIsCreate = ref(false)
const adminTestResult = ref<ZohoImportTestResponse | null>(null)
const userTestResults = ref<Record<string, ZohoImportTestResponse>>({})
const adminDiscoverResult = ref<{ ok: boolean; tools: number } | null>(null)
const userDiscoverResults = ref<Record<string, { ok: boolean; tools: number }>>({})

const editTitle = computed(() => {
  if (editIsCreate.value) return 'Configurer le compte admin'
  if (editRow.value?.is_admin) return 'Modifier le compte admin'
  return "Modifier l'import"
})

onMounted(() => {
  const wanted = route.query.zoho_tab
  if (wanted === 'admin' || wanted === 'users') {
    activeTab.value = wanted
  }
  store.fetchAdmin()
  store.fetchUsers()
})

function goToImport() {
  router.push({
    name: 'google-sheets-import',
    query: { from: 'templates', template_slug: props.templateSlug },
  })
}

function goToAdd() {
  router.push({
    name: 'zoho-import-new',
    params: { slug: props.templateSlug },
    query: { scope: activeTab.value },
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

async function onDiscoverAdmin() {
  if (!store.admin) return
  adminDiscoverResult.value = await store.discoverRow(store.admin.id)
}

async function onDiscoverUser(r: ZohoImportRow) {
  const res = await store.discoverRow(r.id)
  userDiscoverResults.value = { ...userDiscoverResults.value, [r.id]: res }
}

function onSearchUsers(s: string) {
  store.fetchUsers({ page: 1, search: s })
}
</script>
