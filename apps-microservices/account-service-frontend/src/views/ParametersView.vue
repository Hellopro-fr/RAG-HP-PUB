<script setup lang="ts">
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
</script>

<template>
  <div class="p-6 max-w-3xl">
    <h1 class="text-2xl font-semibold mb-4">Paramètres</h1>
    <div class="bg-white dark:bg-gray-900 p-4 rounded shadow space-y-3">
      <div>
        <p class="text-sm text-gray-500 dark:text-gray-400">Connecté en tant que</p>
        <p class="font-mono">{{ auth.user?.email }}</p>
      </div>
      <div>
        <p class="text-sm text-gray-500 dark:text-gray-400">Rôle</p>
        <p>{{ auth.user?.is_admin ? 'admin' : 'user' }}</p>
      </div>
      <p class="text-sm text-gray-500 mt-6">
        Configuration système (TTL par défaut, alertes Slack, audit) gérée via variables d'environnement
        côté backend. Consulter <code class="font-mono">CLAUDE.md</code> du service pour la liste complète.
      </p>
    </div>
  </div>
</template>
