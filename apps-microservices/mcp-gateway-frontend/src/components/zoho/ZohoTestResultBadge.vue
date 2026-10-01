<template>
  <span
    v-if="result"
    :class="[
      'inline-flex items-center gap-1 text-xs rounded-full px-2 py-0.5 font-medium',
      result.ok
        ? 'bg-success-50 text-success-700 dark:bg-success-500/15 dark:text-success-400'
        : 'bg-error-50 text-error-700 dark:bg-error-500/15 dark:text-error-400',
    ]"
  >
    <i :class="result.ok ? 'pi pi-check-circle' : 'pi pi-times-circle'" />
    <template v-if="result.ok">
      {{ result.status_code ?? '?' }} · {{ result.latency_ms }}ms
    </template>
    <template v-else>
      {{ result.error || result.status_code }} · {{ result.latency_ms }}ms
    </template>
  </span>
</template>

<script setup lang="ts">
import type { ZohoImportTestResponse } from '@/types/zoho'
defineProps<{ result: ZohoImportTestResponse | null }>()
</script>
