<template>
  <div>
    <PageBreadcrumb :page-title="template?.name || slug" />

    <!-- Loading state (template metadata not yet fetched) -->
    <div
      v-if="!template && loading"
      class="text-center py-12"
    >
      <i class="pi pi-spinner pi-spin text-2xl text-brand-500" />
    </div>

    <!-- Error / not found -->
    <div
      v-else-if="!template"
      class="text-center py-12 text-gray-500 dark:text-gray-400"
    >
      <i class="pi pi-exclamation-circle text-4xl mb-3 block" />
      <p>Template introuvable.</p>
      <router-link
        :to="{ name: 'templates' }"
        class="text-xs text-brand-500 hover:text-brand-600 mt-2 inline-block"
      >
        Retour au catalogue
      </router-link>
    </div>

    <template v-else>
      <!-- Header: icon + name + subtitle + Add button -->
      <div class="flex items-start justify-between gap-4 mb-6">
        <div class="flex items-center gap-3 min-w-0">
          <div
            v-if="template.icon"
            class="w-12 h-12 rounded-full bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 flex items-center justify-center shrink-0 p-1"
          >
            <img :src="template.icon" :alt="template.name" class="w-8 h-8 object-contain" />
          </div>
          <div
            v-else
            class="w-12 h-12 rounded-full bg-brand-50 dark:bg-brand-500/15 text-brand-500 flex items-center justify-center shrink-0"
          >
            <i class="pi pi-th-large text-xl" />
          </div>
          <div class="min-w-0">
            <h2 class="text-base font-semibold text-gray-900 dark:text-white truncate">
              {{ template.name }}
            </h2>
            <p
              v-if="template.stdio_command"
              class="text-xs text-gray-500 dark:text-gray-400 truncate"
              :title="template.stdio_command"
            >
              Wraps
              <code class="font-mono bg-gray-100 dark:bg-white/5 px-1.5 py-0.5 rounded">
                {{ template.stdio_command }}
              </code>
            </p>
          </div>
        </div>
        <button
          class="px-4 py-2 text-sm font-medium text-white bg-brand-500 hover:bg-brand-600 rounded-md flex items-center gap-2 shrink-0"
          @click="onAdd"
        >
          <i class="pi pi-plus text-xs" />
          Add instance
        </button>
      </div>

      <!-- Description -->
      <p
        v-if="template.description"
        class="text-sm text-gray-600 dark:text-gray-400 mb-6"
      >
        {{ template.description }}
      </p>

      <!-- Required env schema -->
      <section
        v-if="template.required_extra_env && template.required_extra_env.length > 0"
        class="mb-8 bg-white dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-800 p-5"
      >
        <h3 class="text-sm font-semibold text-gray-900 dark:text-white mb-3">
          Variables d'environnement requises
        </h3>
        <ul class="space-y-2">
          <li
            v-for="field in template.required_extra_env"
            :key="field.key"
            class="flex items-center justify-between gap-3 text-xs border border-gray-100 dark:border-gray-800 rounded px-3 py-2"
          >
            <div class="flex items-center gap-3 min-w-0">
              <code class="font-mono bg-gray-100 dark:bg-white/5 text-gray-700 dark:text-gray-300 px-2 py-0.5 rounded shrink-0">
                {{ field.key }}
              </code>
              <span class="text-gray-600 dark:text-gray-400 truncate">
                {{ field.label }}
              </span>
            </div>
            <span
              v-if="field.required"
              class="text-[11px] px-2 py-0.5 rounded-full font-medium bg-error-50 text-error-600 dark:bg-error-500/15 dark:text-error-400 shrink-0"
            >
              (required)
            </span>
          </li>
        </ul>
      </section>

      <!-- Instances section -->
      <section>
        <h3 class="text-sm font-semibold text-gray-900 dark:text-white mb-4">
          Instances ({{ instances.length }})
        </h3>

        <div
          v-if="store.isLoading && instances.length === 0"
          class="text-center py-12"
        >
          <i class="pi pi-spinner pi-spin text-2xl text-brand-500" />
        </div>

        <div
          v-else-if="instances.length === 0"
          class="text-center py-12 text-gray-500 dark:text-gray-400 bg-white dark:bg-gray-900 rounded-lg border border-dashed border-gray-200 dark:border-gray-800"
        >
          <i class="pi pi-inbox text-3xl mb-3 block" />
          <p class="text-sm">
            Aucune instance &mdash; cliquez sur + Add instance pour commencer.
          </p>
        </div>

        <div
          v-else
          class="grid grid-cols-1 xl:grid-cols-2 gap-4"
        >
          <TemplateInstanceCard
            v-for="inst in instances"
            :key="inst.id"
            :inst="inst"
            @restart="onRestart"
            @delete="onDelete"
            @rotate="onRotate"
            @logs="onLogs"
          />
        </div>
      </section>
    </template>

    <!-- Delete confirm dialog -->
    <ConfirmDialog
      :open="!!deletingInstance"
      title="Supprimer l'instance"
      message="Êtes-vous sûr de vouloir supprimer cette instance ? Cette action est irréversible."
      confirm-label="Supprimer"
      @update:open="deletingInstance = null"
      @confirm="confirmDelete"
    />

    <!-- Task 26: AddInstanceModal (showAdd) -->
    <!-- Task 27: RotateCredentialsModal (rotateTarget) -->
    <!-- Task 27: InstanceLogsModal (logsTarget) -->
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useTemplatesStore } from '@/stores/templates'
import { templatesApi } from '@/api/templates'
import { useToast } from '@/composables/useToast'
import PageBreadcrumb from '@/components/common/PageBreadcrumb.vue'
import TemplateInstanceCard from '@/components/templates/TemplateInstanceCard.vue'
import ConfirmDialog from '@/components/shared/ConfirmDialog.vue'
import type { Template, TemplateInstance } from '@/types/templates'

const props = defineProps<{
  slug: string
}>()

const store = useTemplatesStore()
const toast = useToast()

const template = ref<Template | null>(null)
const loading = ref(false)
const showAdd = ref(false)
const rotateTarget = ref<TemplateInstance | null>(null)
const logsTarget = ref<TemplateInstance | null>(null)
const deletingInstance = ref<TemplateInstance | null>(null)

// Defensive filter: the store is global so a stale list from another slug
// could briefly leak through during navigation between templates.
const instances = computed(() =>
  store.instances.filter(i => i.template_slug === props.slug)
)

async function loadAll(slug: string): Promise<void> {
  loading.value = true
  try {
    const [meta] = await Promise.all([
      templatesApi.get(slug),
      store.fetchInstances(slug)
    ])
    template.value = meta
  } catch (err) {
    console.error('Failed to load template:', err)
    template.value = null
    toast.error('Impossible de charger le template')
  } finally {
    loading.value = false
  }
}

async function refetchInstances(): Promise<void> {
  try {
    await store.fetchInstances(props.slug)
  } catch (err) {
    console.error('Failed to refresh instances:', err)
  }
}

onMounted(() => {
  loadAll(props.slug)
})

// Reactively reload when navigating between /admin/templates/:slug routes
// without unmounting (vue-router reuses the component).
watch(
  () => props.slug,
  (next, prev) => {
    if (next && next !== prev) {
      template.value = null
      loadAll(next)
    }
  }
)

function onAdd(): void {
  // Task 26: open AddInstanceModal
  showAdd.value = true
}

async function onRestart(inst: TemplateInstance): Promise<void> {
  try {
    await store.restartInstance(inst.id)
    toast.success('Redémarrage lancé')
    await refetchInstances()
  } catch (err) {
    console.error('Failed to restart instance:', err)
    toast.error('Échec du redémarrage')
  }
}

function onDelete(inst: TemplateInstance): void {
  deletingInstance.value = inst
}

async function confirmDelete(): Promise<void> {
  const target = deletingInstance.value
  if (!target) return
  try {
    await store.deleteInstance(target.id)
    toast.success('Instance supprimée')
    await refetchInstances()
  } catch (err) {
    console.error('Failed to delete instance:', err)
    toast.error('Échec de la suppression')
  } finally {
    deletingInstance.value = null
  }
}

function onRotate(inst: TemplateInstance): void {
  // Task 27: open RotateCredentialsModal
  rotateTarget.value = inst
}

function onLogs(inst: TemplateInstance): void {
  // Task 27: open InstanceLogsModal
  logsTarget.value = inst
}
</script>
