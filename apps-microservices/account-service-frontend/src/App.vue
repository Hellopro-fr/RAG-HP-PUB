<template>
  <ThemeProvider>
    <SidebarProvider>
      <AdminLayout v-if="useAdminLayout">
        <RouterView />
      </AdminLayout>
      <RouterView v-else />
    </SidebarProvider>
  </ThemeProvider>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import ThemeProvider from './components/layout/ThemeProvider.vue'
import SidebarProvider from './components/layout/SidebarProvider.vue'
import AdminLayout from './components/layout/AdminLayout.vue'

const route = useRoute()
const useAdminLayout = computed(() => route.meta.requiresAuth !== false)
</script>
