<script setup lang="ts">
import { onMounted, ref } from 'vue'
import * as auditApi from '@/api/audit'
import type { AuditEntry } from '@/types/audit'

const items = ref<AuditEntry[]>([])
const total = ref(0)
const filterEvent = ref('')
const error = ref('')

async function load() {
  try {
    const r = await auditApi.list({ event: filterEvent.value || undefined }, 50, 0)
    items.value = r.items
    total.value = r.total
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Erreur'
  }
}

onMounted(load)
</script>

<template>
  <div class="p-6">
    <h1 class="text-2xl font-semibold mb-4">Journal d'audit ({{ total }})</h1>
    <div class="flex gap-2 mb-4">
      <select v-model="filterEvent" @change="load" class="h-10 px-3 border rounded dark:bg-gray-900 dark:border-gray-700">
        <option value="">— Tous les événements —</option>
        <option value="login">login</option>
        <option value="login_fail">login_fail</option>
        <option value="token_issue">token_issue</option>
        <option value="token_refresh">token_refresh</option>
        <option value="token_reuse_attack">token_reuse_attack</option>
        <option value="logout">logout</option>
        <option value="webhook_fired">webhook_fired</option>
        <option value="webhook_failed">webhook_failed</option>
      </select>
    </div>
    <div v-if="error" class="mb-4 p-3 bg-red-50 text-red-700 rounded">{{ error }}</div>
    <table class="w-full text-sm bg-white dark:bg-gray-900 rounded shadow">
      <thead class="bg-gray-100 dark:bg-gray-800">
        <tr>
          <th class="px-4 py-2 text-left">Date</th>
          <th class="px-4 py-2 text-left">Évènement</th>
          <th class="px-4 py-2 text-left">Acteur</th>
          <th class="px-4 py-2 text-left">Cible</th>
          <th class="px-4 py-2 text-left">Client</th>
          <th class="px-4 py-2 text-left">IP</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="r in items" :key="r.id" class="border-t">
          <td class="px-4 py-2 font-mono">{{ r.created_at }}</td>
          <td class="px-4 py-2 font-medium">{{ r.event }}</td>
          <td class="px-4 py-2">{{ r.actor_email }}</td>
          <td class="px-4 py-2">{{ r.target_email }}</td>
          <td class="px-4 py-2">{{ r.client_id }}</td>
          <td class="px-4 py-2">{{ r.ip_addr }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
