<template>
  <div class="flex h-screen overflow-hidden">
    <AppSidebar v-model="sidebarOpen" />
    <div class="relative flex flex-1 flex-col overflow-y-auto lg:ml-64">
      <AppHeader @toggle-sidebar="sidebarOpen = !sidebarOpen" />
      <main class="p-6 lg:p-8">
        <slot />
      </main>
    </div>
    <Toast />
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import AppSidebar from './AppSidebar.vue'
import AppHeader from './AppHeader.vue'
import Toast from 'primevue/toast'

const sidebarOpen = ref(false)
</script>
