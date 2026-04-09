<template>
  <ThemeProvider>
    <SidebarProvider>
      <AppLayout v-if="showLayout">
        <RouterView />
      </AppLayout>
      <RouterView v-else />
    </SidebarProvider>
  </ThemeProvider>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { RouterView, useRoute } from 'vue-router';
import AppLayout from '@/components/layout/AppLayout.vue';
import ThemeProvider from '@/components/layout/ThemeProvider.vue';
import SidebarProvider from '@/components/layout/SidebarProvider.vue';

const route = useRoute();

const showLayout = computed(() => {
  return route.meta.requiresAuth !== false;
});
</script>
