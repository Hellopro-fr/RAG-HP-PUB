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
import { useAuthStore } from './stores/auth'

const route = useRoute()
const authStore = useAuthStore()

// Only render the AdminLayout (header + sidebar) once both (a) the resolved
// route opts in to auth AND (b) the user is actually authenticated. Defaulting
// to !== false caused a layout flash on first paint because Vue Router commits
// the START_LOCATION before beforeEach finishes, so the sidebar/header
// painted briefly before the guard redirected to /login.
const useAdminLayout = computed(
  () => route.meta.requiresAuth === true && authStore.isAuthenticated,
)
</script>
