<template>
  <div class="relative group">
    <pre class="bg-gray-900 text-green-400 rounded-lg px-4 py-3 overflow-x-auto text-sm leading-relaxed"><code>{{ code }}</code></pre>
    <button
      class="absolute top-2 right-2 px-2 py-1 text-xs rounded transition-colors"
      :class="copied
        ? 'bg-emerald-600 text-white'
        : 'bg-gray-700 text-gray-300 hover:bg-gray-600 opacity-0 group-hover:opacity-100'"
      @click="handleCopy"
    >
      {{ copied ? 'Copie !' : 'Copier' }}
    </button>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'

const props = defineProps<{ code: string }>()
const emit = defineEmits<{ copy: [code: string] }>()

const copied = ref(false)

function handleCopy() {
  emit('copy', props.code)
  copied.value = true
  setTimeout(() => { copied.value = false }, 1500)
}
</script>
