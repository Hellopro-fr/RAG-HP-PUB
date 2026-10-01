<script setup lang="ts">
const props = defineProps<{ ok?: boolean; at?: string }>()
const isNever = !props.at
const cls = isNever
  ? 'bg-gray-100 text-gray-600'
  : props.ok
    ? 'bg-green-100 text-green-700'
    : 'bg-red-100 text-red-700'
const label = isNever
  ? 'Jamais scanné'
  : props.ok
    ? `OK · ${formatRelative(props.at!)}`
    : `Échec · ${formatRelative(props.at!)}`

function formatRelative(iso: string): string {
  try {
    const d = new Date(iso)
    const diff = (Date.now() - d.getTime()) / 1000
    if (diff < 60) return "à l'instant"
    if (diff < 3600) return `il y a ${Math.floor(diff / 60)} min`
    if (diff < 86400) return `il y a ${Math.floor(diff / 3600)} h`
    return `il y a ${Math.floor(diff / 86400)} j`
  } catch {
    return iso
  }
}
</script>
<template>
  <span class="inline-flex px-2 py-0.5 text-xs font-medium rounded" :class="cls">
    {{ label }}
  </span>
</template>
