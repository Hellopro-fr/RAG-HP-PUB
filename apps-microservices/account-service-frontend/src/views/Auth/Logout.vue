<script setup lang="ts">
import AuthCard from '../../components/auth/AuthCard.vue'
import { onMounted } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
onMounted(() => {
  const target = String(route.query.post_logout_redirect_uri || '/')
  setTimeout(() => window.location.assign(target), 1500)
})
</script>

<template>
  <AuthCard title="Signed out" subtitle="You have been logged out.">
    <p class="text-sm text-gray-500">Redirecting…</p>
  </AuthCard>
</template>
