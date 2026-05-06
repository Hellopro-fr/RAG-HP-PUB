<template>
  <ThemeProvider>
    <DocsLayout v-if="isDocsLayout">
      <RouterView />
    </DocsLayout>
    <AppLayout v-else-if="showLayout">
      <RouterView />
    </AppLayout>
    <RouterView v-else />
  </ThemeProvider>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { RouterView, useRoute } from 'vue-router';
import AppLayout from '@/components/layout/AppLayout.vue';
import DocsLayout from '@/components/layout/DocsLayout.vue';
import ThemeProvider from '@/components/layout/ThemeProvider.vue';
import { useAuthStore } from '@/stores/auth';

const route = useRoute();
const authStore = useAuthStore();

const isDocsLayout = computed(() => {
  return route.meta.layout === 'docs';
});

// Render the protected AppLayout only when (a) the resolved route opts in
// AND (b) the user is actually authenticated. The first-load flash of the
// header + sidebar that appeared on mcp.hellopro.eu came from
// `requiresAuth !== false` defaulting to true on the empty start-location
// route — Vue Router commits the START_LOCATION before beforeEach finishes,
// so AppLayout painted briefly before the guard redirected to /sso/login.
// Anchoring on isAuthenticated suppresses the chrome until checkSession
// lands a user.
const showLayout = computed(() => {
  return route.meta.requiresAuth === true && authStore.isAuthenticated;
});
</script>
