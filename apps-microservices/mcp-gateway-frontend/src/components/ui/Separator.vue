<template>
  <Separator
    :decorative="true"
    :orientation="orientation"
    class="shrink-0 bg-gray-200 dark:bg-gray-800"
    :class="orientation === 'horizontal' ? 'h-px w-full' : 'h-full w-px'"
  />
</template>

<script setup lang="ts">
import { Separator } from 'radix-vue'

withDefaults(
  defineProps<{
    orientation?: 'horizontal' | 'vertical'
  }>(),
  { orientation: 'horizontal' },
)
</script>
