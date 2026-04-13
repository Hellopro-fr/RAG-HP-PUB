<template>
  <span :class="[baseStyles, sizeClass, colorStyles]">
    <slot />
  </span>
</template>

<script setup lang="ts">
import { computed } from 'vue'

type BadgeVariant = 'light' | 'solid'
type BadgeSize = 'sm' | 'md'
type BadgeColor = 'primary' | 'success' | 'error' | 'warning' | 'info'

interface BadgeProps {
  variant?: BadgeVariant
  size?: BadgeSize
  color?: BadgeColor
}

const props = withDefaults(defineProps<BadgeProps>(), {
  variant: 'light',
  color: 'primary',
  size: 'md',
})

const baseStyles =
  'inline-flex items-center px-2.5 py-0.5 justify-center gap-1 rounded-full font-medium'

const sizeStyles: Record<BadgeSize, string> = {
  sm: 'text-xs',
  md: 'text-sm',
}

const variants: Record<BadgeVariant, Record<BadgeColor, string>> = {
  light: {
    primary: 'bg-blue-50 text-blue-600 dark:bg-blue-500/15 dark:text-blue-400',
    success: 'bg-green-50 text-green-600 dark:bg-green-500/15 dark:text-green-500',
    error: 'bg-red-50 text-red-600 dark:bg-red-500/15 dark:text-red-500',
    warning: 'bg-amber-50 text-amber-600 dark:bg-amber-500/15 dark:text-orange-400',
    info: 'bg-sky-50 text-sky-600 dark:bg-sky-500/15 dark:text-sky-500',
  },
  solid: {
    primary: 'bg-blue-500 text-white dark:text-white',
    success: 'bg-green-500 text-white dark:text-white',
    error: 'bg-red-500 text-white dark:text-white',
    warning: 'bg-amber-500 text-white dark:text-white',
    info: 'bg-sky-500 text-white dark:text-white',
  },
}

const sizeClass = computed(() => sizeStyles[props.size])
const colorStyles = computed(() => variants[props.variant][props.color])
</script>
