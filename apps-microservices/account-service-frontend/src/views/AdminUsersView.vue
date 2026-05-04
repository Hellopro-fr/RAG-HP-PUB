<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import * as usersApi from '@/api/users'

const router = useRouter()
const items = ref<usersApi.AdminUser[]>([])
const total = ref(0)
const loading = ref(true)
const error = ref('')

async function load() {
  loading.value = true
  try {
    const r = await usersApi.list(50, 0)
    items.value = r.items
    total.value = r.total
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Erreur'
  } finally {
    loading.value = false
  }
}

async function action(fn: (e: string) => Promise<unknown>, email: string, label: string) {
  if (!confirm(`${label} ${email} ?`)) return
  try {
    await fn(email)
    await load()
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Erreur'
  }
}

onMounted(load)
</script>

<template>
  <div class="p-6">
    <h1 class="text-2xl font-semibold mb-4">Utilisateurs ({{ total }})</h1>
    <div v-if="error" class="mb-4 p-3 bg-red-50 text-red-700 rounded">{{ error }}</div>

    <table class="w-full text-sm bg-white dark:bg-gray-900 rounded shadow">
      <thead class="bg-gray-100 dark:bg-gray-800">
        <tr>
          <th class="px-4 py-2 text-left">Email</th>
          <th class="px-4 py-2 text-left">Nom</th>
          <th class="px-4 py-2">Admin</th>
          <th class="px-4 py-2">Autorisé</th>
          <th class="px-4 py-2 text-left">Dernière connexion</th>
          <th class="px-4 py-2"></th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="u in items" :key="u.email" class="border-t">
          <td class="px-4 py-2 font-mono">{{ u.email }}</td>
          <td class="px-4 py-2">{{ u.display_name }}</td>
          <td class="px-4 py-2 text-center">{{ u.is_admin ? '✔' : '' }}</td>
          <td class="px-4 py-2 text-center">{{ u.is_allowed ? '✔' : '✗' }}</td>
          <td class="px-4 py-2">{{ u.last_login_at ?? '—' }}</td>
          <td class="px-4 py-2 text-right space-x-2">
            <button v-if="!u.is_admin" class="text-blue-600" @click="action(usersApi.promote, u.email, 'Promouvoir')">Promouvoir</button>
            <button v-else class="text-yellow-600" @click="action(usersApi.demote, u.email, 'Rétrograder')">Rétrograder</button>
            <button v-if="u.is_allowed" class="text-red-600" @click="action(usersApi.block, u.email, 'Bloquer')">Bloquer</button>
            <button v-else class="text-green-600" @click="action(usersApi.unblock, u.email, 'Débloquer')">Débloquer</button>
            <button class="text-red-700" @click="action(usersApi.revoke, u.email, 'Révoquer toutes les sessions de')">Révoquer</button>
            <button class="text-gray-600" @click="router.push(`/admin/users/${encodeURIComponent(u.email)}/sessions`)">Sessions</button>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
