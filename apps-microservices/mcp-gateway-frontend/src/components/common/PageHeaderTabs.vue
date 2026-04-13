<template>
  <div class="rounded-2xl border border-gray-200 bg-white dark:border-gray-800 dark:bg-white/[0.03]">
    <!-- Tab bar -->
    <div class="flex items-center justify-between border-b border-gray-100 dark:border-gray-800">
      <div class="flex items-center">
        <button
          v-for="tab in tabs"
          :key="tab.value"
          class="px-5 py-4 text-sm font-medium transition-colors relative"
          :class="
            modelValue === tab.value
              ? 'text-blue-600 dark:text-blue-400'
              : 'text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200'
          "
          @click="emit('update:modelValue', tab.value)"
        >
          {{ tab.label }}
          <span
            v-if="tab.count !== undefined"
            class="ml-2 inline-flex items-center justify-center min-w-[20px] h-5 px-1.5 text-xs font-medium rounded-full"
            :class="
              modelValue === tab.value
                ? 'bg-blue-100 text-blue-600 dark:bg-blue-500/20 dark:text-blue-400'
                : 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300'
            "
          >
            {{ tab.count }}
          </span>
          <!-- Active indicator bar at bottom -->
          <span
            v-if="modelValue === tab.value"
            class="absolute bottom-0 left-0 right-0 h-0.5 bg-blue-500"
          />
        </button>
      </div>
      <div class="flex items-center gap-3 px-4">
        <slot name="actions" />
      </div>
    </div>
    <!-- Content -->
    <div class="p-4 sm:p-6">
      <slot />
    </div>
  </div>
</template>

<script setup lang="ts">
interface Tab {
  label: string
  value: string
  count?: number
}

interface Props {
  tabs: Tab[]
  modelValue: string
}

defineProps<Props>()

const emit = defineEmits<{
  'update:modelValue': [value: string]
}>()
</script>
