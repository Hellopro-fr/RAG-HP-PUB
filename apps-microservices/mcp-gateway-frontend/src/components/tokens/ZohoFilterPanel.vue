<template>
  <div class="space-y-3">
    <!-- Mode select -->
    <div>
      <label for="zoho-filter-mode" class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
        Restriction des appels Zoho
      </label>
      <select
        id="zoho-filter-mode"
        :value="model.mode"
        class="h-11 w-full rounded-lg border border-gray-300 bg-transparent px-4 py-2.5 text-sm text-gray-800 shadow-theme-xs focus:border-brand-300 focus:outline-hidden focus:ring-3 focus:ring-brand-500/10 dark:border-gray-700 dark:bg-gray-900 dark:text-white/90 appearance-none"
        @change="onModeChange(($event.target as HTMLSelectElement).value as ZohoFilter['mode'])"
      >
        <option value="none">Aucune restriction (acc&egrave;s complet)</option>
        <option value="users">Emails autoris&eacute;s</option>
        <option value="creator">Cr&eacute;ateur du jeton uniquement</option>
      </select>
      <p class="text-xs text-gray-400 dark:text-gray-500 mt-1">
        Restreint les appels Zoho aux emails autorisés.
        Pour les serveurs Zoho importés depuis un Google Sheet, le <code>created_by</code>
        du serveur prend précédence (filtre automatique par ligne).
      </p>
    </div>

    <!-- Emails picker -->
    <div v-if="model.mode === 'users'" class="space-y-2">
      <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
        Emails autoris&eacute;s
      </label>
      <div class="flex gap-2">
        <input
          v-model="newEmail"
          type="email"
          placeholder="alice@hellopro.fr"
          class="h-9 flex-1 text-sm rounded-md border border-gray-300 dark:border-gray-600 px-3 bg-white dark:bg-gray-800 dark:text-gray-200 focus:border-brand-300 focus:outline-hidden focus:ring-3 focus:ring-brand-500/10"
          @keyup.enter.prevent="addEmail"
        />
        <button
          type="button"
          class="px-3 text-sm font-medium text-white bg-brand-500 rounded-md hover:bg-brand-600"
          @click="addEmail"
        >
          Ajouter
        </button>
      </div>
      <ul class="flex flex-wrap gap-2">
        <li
          v-for="email in emailsLocal"
          :key="email"
          class="inline-flex items-center gap-1 text-xs bg-gray-100 dark:bg-white/5 text-gray-700 dark:text-gray-300 rounded-full px-2 py-0.5"
        >
          {{ email }}
          <button
            type="button"
            class="text-gray-400 hover:text-error-500"
            aria-label="Retirer"
            @click="removeEmail(email)"
          >&times;</button>
        </li>
      </ul>
      <p v-if="!emailsLocal.length" class="text-xs text-error-500">
        Mode &laquo;&nbsp;users&nbsp;&raquo; requiert au moins un email.
      </p>
    </div>

    <!-- Creator info -->
    <div
      v-if="model.mode === 'creator'"
      class="rounded-md border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900/40 p-3 text-sm text-gray-600 dark:text-gray-400"
    >
      <i class="pi pi-info-circle mr-1" />
      L'adresse email du cr&eacute;ateur du jeton sera utilis&eacute;e comme filtre Zoho lors de la cr&eacute;ation.
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import type { ZohoFilter } from '@/types/leexi'

const props = defineProps<{
  modelValue: ZohoFilter
}>()

const emit = defineEmits<{ (e: 'update:modelValue', value: ZohoFilter): void }>()

const model = computed<ZohoFilter>(() => props.modelValue)

// Local email list — kept in sync with the parent's allowed_emails.
const emailsLocal = ref<string[]>(props.modelValue?.allowed_emails ?? [])
const newEmail = ref('')

watch(
  () => props.modelValue,
  (next) => {
    emailsLocal.value = next?.allowed_emails ?? []
  },
)

function onModeChange(mode: ZohoFilter['mode']) {
  const next: ZohoFilter = { mode }
  if (mode === 'users') next.allowed_emails = emailsLocal.value
  emit('update:modelValue', next)
}

function addEmail() {
  const v = newEmail.value.trim()
  if (!v) return
  if (emailsLocal.value.includes(v)) {
    newEmail.value = ''
    return
  }
  emailsLocal.value = [...emailsLocal.value, v]
  newEmail.value = ''
  emit('update:modelValue', { ...model.value, allowed_emails: emailsLocal.value })
}

function removeEmail(email: string) {
  emailsLocal.value = emailsLocal.value.filter(e => e !== email)
  emit('update:modelValue', { ...model.value, allowed_emails: emailsLocal.value })
}
</script>
