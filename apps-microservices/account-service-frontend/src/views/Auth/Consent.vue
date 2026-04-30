<script setup lang="ts">
import AuthCard from '../../components/auth/AuthCard.vue'
import { useRoute } from 'vue-router'
const route = useRoute()
function deny() {
  const r = String(route.query.redirect_uri || '/')
  const s = String(route.query.state || '')
  window.location.assign(`${r}?error=access_denied&state=${s}`)
}
</script>

<template>
  <AuthCard title="Authorize access"
            subtitle="An application is requesting access to your account.">
    <p class="text-sm text-gray-700 dark:text-gray-200">
      Allow this application to access your account information?
    </p>
    <div class="mt-6 flex gap-3">
      <button class="flex-1 rounded-md bg-indigo-600 px-4 py-2 text-white"
              disabled>
        Allow (handled by server)
      </button>
      <button class="flex-1 rounded-md bg-gray-200 px-4 py-2" @click="deny">
        Deny
      </button>
    </div>
  </AuthCard>
</template>
