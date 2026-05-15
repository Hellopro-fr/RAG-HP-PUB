<template>
  <div>
    <div class="mb-6 flex items-center gap-4">
      <BaseButton variant="ghost" size="sm" @click="goBack">
        <i class="pi pi-arrow-left text-xs mr-1" />
        Retour
      </BaseButton>
      <h1 class="text-2xl font-bold text-gray-900 dark:text-white">
        {{ row?.name || 'Import Zoho' }}
      </h1>
      <span
        v-if="row"
        class="text-xs px-2 py-0.5 rounded-full font-medium"
        :class="row.is_admin
          ? 'bg-brand-100 text-brand-700 dark:bg-brand-500/20 dark:text-brand-400'
          : 'bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300'"
      >
        {{ row.is_admin ? 'Compte admin' : 'Utilisateur' }}
      </span>
    </div>

    <div v-if="loading" class="flex items-center justify-center py-20">
      <i class="pi pi-spinner pi-spin text-2xl text-gray-400 dark:text-gray-500" />
    </div>

    <div
      v-else-if="!row"
      class="text-center py-12 text-gray-500 dark:text-gray-400 bg-white dark:bg-gray-900 rounded-lg border border-dashed border-gray-200 dark:border-gray-800"
    >
      <i class="pi pi-exclamation-circle text-4xl mb-3 block" />
      <p class="text-sm">Import introuvable.</p>
      <button
        class="mt-3 text-xs text-brand-500 hover:text-brand-600"
        @click="goBack"
      >
        Retour au template
      </button>
    </div>

    <template v-else>
      <section class="bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-800 p-5 mb-6">
        <h2 class="text-sm font-semibold text-gray-900 dark:text-white mb-3">Métadonnées</h2>
        <dl class="divide-y divide-gray-100 dark:divide-gray-800 text-sm">
          <div class="py-2 grid grid-cols-3 gap-4">
            <dt class="text-gray-500 dark:text-gray-400">Nom</dt>
            <dd class="text-gray-900 dark:text-white col-span-2">{{ row.name }}</dd>
          </div>
          <div class="py-2 grid grid-cols-3 gap-4">
            <dt class="text-gray-500 dark:text-gray-400">URL</dt>
            <dd class="text-gray-900 dark:text-white col-span-2 break-all">{{ row.url }}</dd>
          </div>
          <div v-if="!row.is_admin" class="py-2 grid grid-cols-3 gap-4">
            <dt class="text-gray-500 dark:text-gray-400">Créé par</dt>
            <dd class="text-gray-900 dark:text-white col-span-2">{{ row.created_by }}</dd>
          </div>
          <div class="py-2 grid grid-cols-3 gap-4">
            <dt class="text-gray-500 dark:text-gray-400">Actif</dt>
            <dd class="text-gray-900 dark:text-white col-span-2">{{ row.is_active ? 'oui' : 'non' }}</dd>
          </div>
          <div class="py-2 grid grid-cols-3 gap-4">
            <dt class="text-gray-500 dark:text-gray-400">Template</dt>
            <dd class="text-gray-900 dark:text-white col-span-2 font-mono text-xs">{{ row.template_slug || '—' }}</dd>
          </div>
          <div class="py-2 grid grid-cols-3 gap-4">
            <dt class="text-gray-500 dark:text-gray-400">Headers</dt>
            <dd class="text-gray-900 dark:text-white col-span-2 font-mono text-xs">
              {{ row.auth_header_keys.length ? row.auth_header_keys.join(', ') : '—' }}
            </dd>
          </div>
          <div class="py-2 grid grid-cols-3 gap-4">
            <dt class="text-gray-500 dark:text-gray-400">Créé le</dt>
            <dd class="text-gray-900 dark:text-white col-span-2">{{ formatDate(row.created_at) }}</dd>
          </div>
          <div class="py-2 grid grid-cols-3 gap-4">
            <dt class="text-gray-500 dark:text-gray-400">Modifié le</dt>
            <dd class="text-gray-900 dark:text-white col-span-2">{{ formatDate(row.updated_at) }}</dd>
          </div>
        </dl>
      </section>

      <section class="bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-800 p-5 mb-6">
        <h2 class="text-sm font-semibold text-gray-900 dark:text-white mb-3">Test &amp; découverte</h2>
        <div class="flex items-center gap-3 flex-wrap">
          <button
            :class="NEUTRAL_BUTTON_CLASS"
            :disabled="testing"
            @click="onTest"
          >
            <i class="pi pi-bolt text-xs" />
            Tester
          </button>
          <button
            :class="BRAND_BUTTON_CLASS"
            :disabled="discovering"
            @click="onDiscover"
          >
            <i class="pi pi-sync text-xs" />
            Découvrir
          </button>
          <ZohoTestResultBadge v-if="testResult" :result="testResult" />
          <span
            v-if="discoverResult"
            class="text-xs px-2 py-0.5 rounded-full font-medium"
            :class="discoverResult.ok
              ? 'bg-success-100 text-success-700 dark:bg-success-500/20 dark:text-success-400'
              : 'bg-error-100 text-error-700 dark:bg-error-500/20 dark:text-error-400'"
          >
            Découverte : {{ discoverResult.tools }} outils
          </span>
        </div>
      </section>

      <section class="bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-800 p-5">
        <h2 class="text-sm font-semibold text-gray-900 dark:text-white mb-3">
          Outils ({{ tools.length }})
        </h2>
        <div
          v-if="tools.length === 0"
          class="text-center py-8 text-sm text-gray-500 dark:text-gray-400"
        >
          Aucun outil découvert. Lancez « Découvrir » pour peupler le catalogue.
        </div>
        <ul v-else class="space-y-2">
          <li
            v-for="tool in tools"
            :key="tool.name"
            class="border border-gray-100 dark:border-gray-800 rounded-md p-3"
          >
            <div class="text-sm font-medium text-gray-900 dark:text-white">{{ tool.name }}</div>
            <p
              v-if="tool.description"
              class="text-xs text-gray-600 dark:text-gray-400 mt-1"
            >
              {{ tool.description }}
            </p>
            <details class="mt-2">
              <summary class="text-xs text-brand-500 cursor-pointer">Voir le schéma</summary>
              <pre class="mt-2 text-xs font-mono whitespace-pre-wrap bg-gray-50 dark:bg-white/5 p-2 rounded">{{ prettySchema(tool.input_schema) }}</pre>
            </details>
          </li>
        </ul>
      </section>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { zohoImportsApi } from '@/api/zohoImports'
import { useZohoImportsStore } from '@/stores/zohoImports'
import { useToast } from '@/composables/useToast'
import BaseButton from '@/components/ui/BaseButton.vue'
import ZohoTestResultBadge from '@/components/zoho/ZohoTestResultBadge.vue'
import { toErrorMessage } from '@/utils/error'
import type { ZohoImportRow, ZohoImportTool, ZohoImportTestResponse } from '@/types/zoho'

const props = defineProps<{ slug: string; id: string }>()

const NEUTRAL_BUTTON_CLASS = 'px-3 py-1.5 text-sm rounded-md border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-white/5 inline-flex items-center gap-2 disabled:opacity-50'
const BRAND_BUTTON_CLASS = 'px-3 py-1.5 text-sm rounded-md border border-brand-300 dark:border-brand-700 text-brand-600 dark:text-brand-400 hover:bg-brand-50 dark:hover:bg-brand-500/10 inline-flex items-center gap-2 disabled:opacity-50'

const router = useRouter()
const store = useZohoImportsStore()
const toast = useToast()

const loading = ref(true)
const row = ref<ZohoImportRow | null>(null)
const tools = ref<ZohoImportTool[]>([])
const testResult = ref<ZohoImportTestResponse | null>(null)
const discoverResult = ref<{ ok: boolean; tools: number } | null>(null)
const testing = ref(false)
const discovering = ref(false)

onMounted(async () => {
  try {
    row.value = await zohoImportsApi.getByID(props.id)
  } catch (err) {
    row.value = null
    toast.error(toErrorMessage(err, 'Erreur lors du chargement de la ligne'))
  }
  if (row.value) {
    try {
      const resp = await zohoImportsApi.listTools(props.id)
      tools.value = resp.tools
    } catch (err) {
      tools.value = []
      toast.error(toErrorMessage(err, 'Erreur lors du chargement du catalogue'))
    }
  }
  loading.value = false
})

function goBack() {
  router.push({ name: 'template-detail', params: { slug: props.slug } })
}

function formatDate(iso: string): string {
  if (!iso) return ''
  try {
    return new Date(iso).toLocaleString('fr-FR')
  } catch {
    return iso
  }
}

function prettySchema(raw: string): string {
  if (!raw) return ''
  try {
    return JSON.stringify(JSON.parse(raw), null, 2)
  } catch {
    return raw
  }
}

async function onTest() {
  testing.value = true
  try {
    testResult.value = await store.testRow(props.id)
  } catch (err) {
    toast.error(toErrorMessage(err, 'Échec du test'))
  } finally {
    testing.value = false
  }
}

async function onDiscover() {
  discovering.value = true
  try {
    discoverResult.value = await store.discoverRow(props.id)
    if (discoverResult.value?.ok) {
      const resp = await zohoImportsApi.listTools(props.id)
      tools.value = resp.tools
    }
  } catch (err) {
    toast.error(toErrorMessage(err, 'Échec de la découverte'))
  } finally {
    discovering.value = false
  }
}
</script>
