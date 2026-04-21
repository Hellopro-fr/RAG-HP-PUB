<template>
  <div>
    <PageBreadcrumb :page-title="`Template: ${slug}`" />
    <div class="p-8 text-center text-gray-500 dark:text-gray-400">
      <i class="pi pi-file-edit text-3xl mb-3 block" />
      <p class="text-base">Template detail (coming soon)</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import PageBreadcrumb from '@/components/common/PageBreadcrumb.vue'

defineProps<{
  slug: string
}>()
</script>
