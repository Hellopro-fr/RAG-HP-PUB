<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import * as servicesApi from '@/api/services'
import type { OAuth2Client } from '@/types/oauth2'

const router = useRouter()
const items = ref<OAuth2Client[]>([])
const total = ref(0)
const loading = ref(true)
const error = ref('')
const limit = 20
const offset = ref(0)

async function load() {
  loading.value = true
  error.value = ''
  try {
    const r = await servicesApi.list(limit, offset.value)
    items.value = r.items
    total.value = r.total
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Erreur de chargement'
  } finally {
    loading.value = false
  }
}

onMounted(load)

function nextPage() { offset.value += limit; load() }
function prevPage() { offset.value = Math.max(0, offset.value - limit); load() }
</script>

<template>
  <div class="p-6">
    <div class="flex items-center justify-between mb-4">
      <h1 class="text-2xl font-semibold">Services OAuth2</h1>
      <button class="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700" @click="router.push('/admin/services/new')">
        + Nouveau service
      </button>
    </div>

    <div v-if="error" class="mb-4 p-3 bg-red-50 text-red-700 rounded-md">{{ error }}</div>

    <div class="bg-white dark:bg-gray-900 rounded-lg shadow overflow-x-auto">
      <table class="w-full text-sm">
        <thead class="bg-gray-100 dark:bg-gray-800">
          <tr>
            <th class="px-4 py-2 text-left">Nom</th>
            <th class="px-4 py-2 text-left">client_id</th>
            <th class="px-4 py-2 text-left">Redirect URIs</th>
            <th class="px-4 py-2 text-left">TTL token</th>
            <th class="px-4 py-2 text-left">Actif</th>
            <th class="px-4 py-2"></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="c in items" :key="c.id" class="border-t">
            <td class="px-4 py-2 font-medium">{{ c.name }}</td>
            <td class="px-4 py-2 font-mono">{{ c.client_id.slice(0, 12) }}…</td>
            <td class="px-4 py-2">{{ c.redirect_uris?.length ?? 0 }}</td>
            <td class="px-4 py-2">{{ c.token_ttl_s }}s</td>
            <td class="px-4 py-2">
              <span :class="c.is_active ? 'text-green-600' : 'text-red-600'">
                {{ c.is_active ? 'oui' : 'non' }}
              </span>
            </td>
            <td class="px-4 py-2 text-right">
              <button class="text-blue-600 hover:underline" @click="router.push(`/admin/services/${c.id}/edit`)">
                Modifier
              </button>
            </td>
          </tr>
          <tr v-if="!loading && items.length === 0">
            <td colspan="6" class="px-4 py-8 text-center text-gray-500">Aucun service</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="mt-4 flex justify-between items-center text-sm">
      <span>{{ total }} service(s)</span>
      <div class="space-x-2">
        <button class="px-3 py-1 border rounded" :disabled="offset === 0" @click="prevPage">Précédent</button>
        <button class="px-3 py-1 border rounded" :disabled="offset + limit >= total" @click="nextPage">Suivant</button>
      </div>
    </div>
  </div>
</template>
