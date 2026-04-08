<template>
  <div class="min-h-screen bg-gray-50">
    <AppNavbar />
    <main class="max-w-7xl mx-auto px-6 py-8">
      <slot />
    </main>
    <Toast />
  </div>
</template>

<script setup lang="ts">
import AppNavbar from './AppNavbar.vue'
import Toast from 'primevue/toast'
</script>
