<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import * as usersApi from '@/api/users'

const route = useRoute()
const email = String(route.params.email)
const items = ref<usersApi.AdminSession[]>([])
const error = ref('')

async function load() {
  try { items.value = (await usersApi.listSessions(email)).items }
  catch (e) { error.value = e instanceof Error ? e.message : 'Erreur' }
}
async function revoke(sid: string) {
  if (!confirm('Révoquer cette session ?')) return
  try { await usersApi.revokeSession(sid); await load() }
  catch (e) { error.value = e instanceof Error ? e.message : 'Erreur' }
}
onMounted(load)
</script>

<template>
  <div class="p-6">
    <h1 class="text-2xl font-semibold mb-4">Sessions de {{ email }}</h1>
    <div v-if="error" class="mb-4 p-3 bg-red-50 text-red-700 rounded">{{ error }}</div>
    <table class="w-full text-sm bg-white dark:bg-gray-900 rounded shadow">
      <thead class="bg-gray-100 dark:bg-gray-800">
        <tr>
          <th class="px-4 py-2 text-left">SID</th>
          <th class="px-4 py-2 text-left">Client</th>
          <th class="px-4 py-2 text-left">Créée</th>
          <th class="px-4 py-2 text-left">Expire</th>
          <th class="px-4 py-2">Révoquée</th>
          <th class="px-4 py-2"></th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="s in items" :key="s.id" class="border-t">
          <td class="px-4 py-2 font-mono">{{ s.sid.slice(0, 12) }}…</td>
          <td class="px-4 py-2">{{ s.client_id }}</td>
          <td class="px-4 py-2">{{ s.created_at }}</td>
          <td class="px-4 py-2">{{ s.expires_at }}</td>
          <td class="px-4 py-2 text-center">{{ s.revoked ? `oui (${s.revoked_reason})` : 'non' }}</td>
          <td class="px-4 py-2 text-right">
            <button v-if="!s.revoked" class="text-red-600" @click="revoke(s.sid)">Révoquer</button>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
