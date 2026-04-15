<template>
  <div>
    <div
      class="flex items-center gap-2 px-3 py-2 border rounded-lg cursor-pointer transition-colors"
      :class="open
        ? 'border-brand-500 ring-2 ring-brand-500/20'
        : 'border-gray-300 dark:border-gray-600 hover:border-gray-400'"
      @click="open = !open"
    >
      <i v-if="modelValue" :class="`pi ${modelValue}`" class="text-sm text-brand-500" />
      <span class="text-sm text-gray-700 dark:text-gray-300 flex-1 truncate">
        {{ modelValue || 'Choisir une icone...' }}
      </span>
      <i class="pi pi-chevron-down text-xs text-gray-400 transition-transform" :class="{ 'rotate-180': open }" />
    </div>

    <div v-if="open" class="mt-2 rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 shadow-lg max-h-64 overflow-hidden">
      <!-- Search -->
      <div class="p-2 border-b border-gray-100 dark:border-gray-800">
        <input
          v-model="search"
          type="text"
          placeholder="Rechercher..."
          class="w-full text-xs border border-gray-300 dark:border-gray-600 rounded px-2 py-1.5 bg-white dark:bg-gray-800 dark:text-gray-200"
          @click.stop
        />
      </div>
      <!-- Grid -->
      <div class="p-2 overflow-y-auto max-h-48 grid grid-cols-8 gap-1">
        <button
          v-for="icon in filteredIcons"
          :key="icon"
          type="button"
          class="w-8 h-8 flex items-center justify-center rounded transition-colors"
          :class="modelValue === icon
            ? 'bg-brand-100 dark:bg-brand-500/20 text-brand-600 dark:text-brand-400'
            : 'hover:bg-gray-100 dark:hover:bg-gray-800 text-gray-600 dark:text-gray-400'"
          :title="icon"
          @click="select(icon)"
        >
          <i :class="`pi ${icon}`" class="text-sm" />
        </button>
      </div>
      <div v-if="!filteredIcons.length" class="p-3 text-center text-xs text-gray-400">
        Aucune icone trouvee
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'

defineProps<{
  modelValue: string
}>()

const emit = defineEmits<{
  'update:modelValue': [value: string]
}>()

const open = ref(false)
const search = ref('')

const icons = [
  'pi-align-center', 'pi-align-justify', 'pi-align-left', 'pi-align-right',
  'pi-arrow-down', 'pi-arrow-left', 'pi-arrow-right', 'pi-arrow-up',
  'pi-ban', 'pi-bars', 'pi-bell', 'pi-bolt', 'pi-book', 'pi-bookmark',
  'pi-box', 'pi-briefcase', 'pi-building', 'pi-calendar',
  'pi-camera', 'pi-car', 'pi-chart-bar', 'pi-chart-line', 'pi-chart-pie',
  'pi-check', 'pi-check-circle', 'pi-chevron-down', 'pi-chevron-left',
  'pi-chevron-right', 'pi-chevron-up', 'pi-circle', 'pi-clipboard',
  'pi-clock', 'pi-clone', 'pi-cloud', 'pi-cloud-download', 'pi-cloud-upload',
  'pi-code', 'pi-cog', 'pi-comment', 'pi-comments', 'pi-compass',
  'pi-copy', 'pi-credit-card', 'pi-database', 'pi-desktop',
  'pi-directions', 'pi-download', 'pi-ellipsis-h', 'pi-ellipsis-v',
  'pi-envelope', 'pi-eraser', 'pi-exclamation-circle', 'pi-exclamation-triangle',
  'pi-external-link', 'pi-eye', 'pi-eye-slash', 'pi-file',
  'pi-file-edit', 'pi-file-export', 'pi-file-import', 'pi-file-pdf',
  'pi-filter', 'pi-flag', 'pi-folder', 'pi-folder-open',
  'pi-forward', 'pi-gift', 'pi-globe', 'pi-hammer',
  'pi-hashtag', 'pi-heart', 'pi-history', 'pi-home',
  'pi-id-card', 'pi-image', 'pi-images', 'pi-inbox',
  'pi-info', 'pi-info-circle', 'pi-key', 'pi-language',
  'pi-link', 'pi-list', 'pi-lock', 'pi-lock-open',
  'pi-map', 'pi-map-marker', 'pi-megaphone', 'pi-microphone',
  'pi-microsoft', 'pi-minus', 'pi-minus-circle', 'pi-mobile',
  'pi-money-bill', 'pi-moon', 'pi-palette', 'pi-paperclip',
  'pi-pause', 'pi-pencil', 'pi-percentage', 'pi-phone',
  'pi-play', 'pi-plus', 'pi-plus-circle', 'pi-power-off',
  'pi-print', 'pi-question', 'pi-question-circle', 'pi-receipt',
  'pi-refresh', 'pi-replay', 'pi-save', 'pi-search',
  'pi-send', 'pi-server', 'pi-share-alt', 'pi-shield',
  'pi-shopping-bag', 'pi-shopping-cart', 'pi-sign-in', 'pi-sign-out',
  'pi-sitemap', 'pi-slack', 'pi-sliders-h', 'pi-sliders-v',
  'pi-sort', 'pi-sort-alpha-down', 'pi-sort-alpha-up', 'pi-spinner',
  'pi-star', 'pi-star-fill', 'pi-stop', 'pi-stopwatch',
  'pi-sun', 'pi-sync', 'pi-table', 'pi-tablet',
  'pi-tag', 'pi-tags', 'pi-th-large', 'pi-thumbs-down',
  'pi-thumbs-up', 'pi-ticket', 'pi-times', 'pi-times-circle',
  'pi-trash', 'pi-truck', 'pi-twitter', 'pi-undo',
  'pi-unlock', 'pi-upload', 'pi-user', 'pi-user-edit',
  'pi-user-minus', 'pi-user-plus', 'pi-users', 'pi-verified',
  'pi-video', 'pi-volume-down', 'pi-volume-off', 'pi-volume-up',
  'pi-wallet', 'pi-wifi', 'pi-wrench',
]

const filteredIcons = computed(() => {
  if (!search.value) return icons
  const q = search.value.toLowerCase()
  return icons.filter(i => i.includes(q))
})

function select(icon: string) {
  emit('update:modelValue', icon)
  open.value = false
  search.value = ''
}
</script>
