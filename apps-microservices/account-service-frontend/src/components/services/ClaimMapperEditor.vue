<script setup lang="ts">
import { computed } from 'vue'

interface Mapping { user_field: string; claim_name: string }

const props = defineProps<{ modelValue: Record<string, string> }>()
const emit = defineEmits<{ (e: 'update:modelValue', v: Record<string, string>): void }>()

const rows = computed<Mapping[]>(() =>
  Object.entries(props.modelValue ?? {}).map(([user_field, claim_name]) => ({ user_field, claim_name }))
)

function add() {
  emit('update:modelValue', { ...props.modelValue, '': '' })
}
function remove(field: string) {
  const copy = { ...props.modelValue }
  delete copy[field]
  emit('update:modelValue', copy)
}
function setField(oldField: string, newField: string) {
  const copy: Record<string, string> = {}
  for (const [k, v] of Object.entries(props.modelValue)) {
    copy[k === oldField ? newField : k] = v
  }
  emit('update:modelValue', copy)
}
function setClaim(field: string, claim: string) {
  emit('update:modelValue', { ...props.modelValue, [field]: claim })
}
</script>

<template>
  <div class="space-y-2">
    <div v-for="row in rows" :key="row.user_field" class="flex gap-2">
      <select
        :value="row.user_field"
        @change="setField(row.user_field, ($event.target as HTMLSelectElement).value)"
        class="h-10 px-3 border rounded dark:bg-gray-900 dark:border-gray-700"
      >
        <option value="">— champ utilisateur —</option>
        <option value="email">email</option>
        <option value="display_name">display_name</option>
        <option value="is_admin">is_admin</option>
      </select>
      <input
        :value="row.claim_name"
        @input="setClaim(row.user_field, ($event.target as HTMLInputElement).value)"
        placeholder="claim JWT"
        class="flex-1 h-10 px-3 border rounded dark:bg-gray-900 dark:border-gray-700"
      />
      <button type="button" class="text-red-600" @click="remove(row.user_field)">×</button>
    </div>
    <button type="button" class="text-sm text-blue-600" @click="add">+ Ajouter un mapping</button>
  </div>
</template>
