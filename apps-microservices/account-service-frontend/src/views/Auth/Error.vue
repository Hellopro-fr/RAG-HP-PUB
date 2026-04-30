<script setup lang="ts">
import AuthCard from '../../components/auth/AuthCard.vue'
import { useRoute } from 'vue-router'
const route = useRoute()
</script>

<template>
  <AuthCard title="Something went wrong">
    <p class="text-sm text-gray-700 dark:text-gray-200">
      {{ route.query.message || 'An unexpected error occurred.' }}
    </p>
    <p class="mt-4">
      <a class="text-indigo-600 hover:underline" href="/signin">Back to sign in</a>
    </p>
  </AuthCard>
</template>
