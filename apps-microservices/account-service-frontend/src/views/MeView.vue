<script setup lang="ts">
import { useAuthStore } from '@/stores/auth'
import { useRouter } from 'vue-router'

const auth = useAuthStore()
const router = useRouter()

async function logout() {
  await auth.logout()
  router.push('/login')
}
</script>

<template>
  <div class="p-6 max-w-xl">
    <h1 class="text-2xl font-semibold mb-4">Mon profil</h1>
    <div class="bg-white dark:bg-gray-900 p-4 rounded shadow space-y-2">
      <p><strong>Email :</strong> {{ auth.user?.email }}</p>
      <p><strong>Nom :</strong> {{ auth.user?.display_name }}</p>
      <p><strong>Admin :</strong> {{ auth.user?.is_admin ? 'oui' : 'non' }}</p>
    </div>
    <button class="mt-4 px-4 py-2 bg-red-600 text-white rounded hover:bg-red-700" @click="logout">
      Se déconnecter
    </button>
  </div>
</template>
