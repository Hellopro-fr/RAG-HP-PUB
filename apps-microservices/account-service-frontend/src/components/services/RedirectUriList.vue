<script setup lang="ts">
import { computed } from 'vue'
const props = defineProps<{ modelValue: string[] }>()
const emit = defineEmits<{ (e: 'update:modelValue', v: string[]): void }>()

const uris = computed({ get: () => props.modelValue, set: (v) => emit('update:modelValue', v) })

function add() { uris.value = [...uris.value, ''] }
function remove(i: number) { uris.value = uris.value.filter((_, idx) => idx !== i) }
function update(i: number, v: string) {
  const copy = [...uris.value]
  copy[i] = v
  uris.value = copy
}
function isValid(u: string): boolean {
  if (!u) return true
  return /^https?:\/\//.test(u)
}
</script>

<template>
  <div class="space-y-2">
    <div v-for="(u, i) in uris" :key="i" class="flex gap-2">
      <input
        :value="u"
        @input="update(i, ($event.target as HTMLInputElement).value)"
        type="url"
        placeholder="https://service.example/callback"
        class="flex-1 h-10 px-3 border rounded dark:bg-gray-900 dark:border-gray-700"
        :class="isValid(u) ? '' : 'border-red-500'"
      />
      <button type="button" class="px-3 py-1 text-red-600" @click="remove(i)">×</button>
    </div>
    <button type="button" class="text-sm text-blue-600" @click="add">+ Ajouter une URI</button>
  </div>
</template>
