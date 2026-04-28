<template>
  <div>
    <!-- Page header (full width) -->
    <div class="mb-6 flex items-center gap-4">
      <button
        type="button"
        class="inline-flex items-center gap-1.5 text-sm text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white"
        @click="router.push({ name: 'template-detail', params: { slug } })"
      >
        <i class="pi pi-arrow-left text-xs" />
        Retour
      </button>
      <h1 class="text-2xl font-bold text-gray-900 dark:text-white">
        {{ template ? `Nouvelle instance ${template.name}` : 'Nouvelle instance' }}
      </h1>
    </div>

    <div class="max-w-3xl mx-auto">
      <!-- Loading state -->
      <div v-if="loading" class="flex items-center justify-center py-20">
        <i class="pi pi-spinner pi-spin text-2xl text-gray-400 dark:text-gray-500" />
      </div>

      <!-- Error / not found -->
      <div
        v-else-if="!template"
        class="text-center py-20 text-gray-500 dark:text-gray-400"
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
        <!-- Step tabs -->
        <StepTabs
          :steps="stepLabels"
          :current-step="currentStep"
          :completed-steps="completedStepsArray"
          @update:current-step="goToStep"
        />

        <!-- Form content -->
        <div class="bg-white dark:bg-gray-900 rounded-lg shadow-theme-xs border border-gray-200 dark:border-gray-800 p-6">
          <!-- Step 0: Informations de base -->
          <div v-show="currentStep === 0" class="space-y-4">
            <!-- Name -->
            <div>
              <label for="form-name" class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Nom <span class="text-red-500">*</span>
              </label>
              <input
                id="form-name"
                v-model="form.name"
                type="text"
                maxlength="255"
                autocomplete="off"
                class="h-11 w-full rounded-lg border border-gray-300 bg-transparent px-4 py-2.5 text-sm text-gray-800 shadow-theme-xs placeholder:text-gray-400 focus:border-brand-300 focus:outline-hidden focus:ring-3 focus:ring-brand-500/10 dark:border-gray-700 dark:bg-gray-900 dark:text-white/90 dark:placeholder:text-white/30"
                placeholder="Ex: projet-ventes-europe"
              />
            </div>

            <!-- Required extra env -->
            <div
              v-if="template.required_extra_env && template.required_extra_env.length > 0"
              class="space-y-3 border border-gray-200 dark:border-gray-800 rounded-md p-4"
            >
              <p class="text-xs font-semibold text-gray-700 dark:text-gray-300">
                Variables d'environnement
              </p>
              <div
                v-for="field in template.required_extra_env"
                :key="field.key"
                class="space-y-1"
              >
                <label
                  :for="`env-${field.key}`"
                  class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1"
                >
                  {{ field.label }}
                  <code class="ml-1 font-mono text-[11px] text-gray-500 dark:text-gray-400">
                    {{ field.key }}
                  </code>
                  <span v-if="field.required" class="text-red-500">*</span>
                </label>
                <input
                  :id="`env-${field.key}`"
                  v-model="form.extra_env[field.key]"
                  type="text"
                  :required="field.required"
                  autocomplete="off"
                  class="h-11 w-full rounded-lg border border-gray-300 bg-transparent px-4 py-2.5 text-sm text-gray-800 shadow-theme-xs placeholder:text-gray-400 focus:border-brand-300 focus:outline-hidden focus:ring-3 focus:ring-brand-500/10 dark:border-gray-700 dark:bg-gray-900 dark:text-white/90 dark:placeholder:text-white/30"
                />
              </div>
            </div>

            <!-- Service account JSON file -->
            <div>
              <label
                for="instance-credentials"
                class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1"
              >
                Clé JSON du compte de service <span class="text-red-500">*</span>
              </label>
              <input
                id="instance-credentials"
                type="file"
                accept="application/json,.json"
                class="block w-full text-sm text-gray-700 dark:text-gray-300 file:mr-3 file:py-2 file:px-3 file:rounded file:border-0 file:text-xs file:font-medium file:bg-brand-50 file:text-brand-600 dark:file:bg-brand-500/15 dark:file:text-brand-400 hover:file:bg-brand-100 dark:hover:file:bg-brand-500/25"
                @change="onFile"
              />
              <p
                v-if="fileInfo"
                class="mt-2 text-xs text-success-600 dark:text-success-400 flex items-center gap-1"
              >
                <i class="pi pi-check-circle text-[11px]" />
                {{ fileInfo }}
              </p>
              <p
                v-if="fileError"
                class="mt-2 text-xs text-error-600 dark:text-error-400 flex items-center gap-1"
              >
                <i class="pi pi-exclamation-triangle text-[11px]" />
                {{ fileError }}
              </p>
              <p class="mt-1 text-[11px] text-gray-500 dark:text-gray-400">
                Fichier JSON (max 16 Ko). Le contenu ne quitte jamais le navigateur tant que vous ne cliquez pas sur Créer.
              </p>
            </div>
          </div>

          <!-- Step 1: Tags et configuration -->
          <div v-show="currentStep === 1" class="space-y-4">
            <!-- Tags -->
            <div>
              <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Tags</label>
              <div class="flex flex-wrap gap-1 mb-2" v-if="form.tags.length">
                <span
                  v-for="tag in form.tags"
                  :key="tag"
                  class="inline-flex items-center gap-1 text-xs bg-brand-100 dark:bg-brand-500/20 text-brand-700 dark:text-brand-400 px-2 py-0.5 rounded-full"
                >
                  {{ tag }}
                  <button type="button" class="hover:text-brand-900 dark:hover:text-brand-300" @click="removeTag(tag)">
                    <i class="pi pi-times text-[10px]" />
                  </button>
                </span>
              </div>
              <div class="relative">
                <input
                  v-model="tagSearch"
                  type="text"
                  class="h-11 w-full rounded-lg border border-gray-300 bg-transparent px-4 py-2.5 text-sm text-gray-800 shadow-theme-xs placeholder:text-gray-400 focus:border-brand-300 focus:outline-hidden focus:ring-3 focus:ring-brand-500/10 dark:border-gray-700 dark:bg-gray-900 dark:text-white/90 dark:placeholder:text-white/30"
                  placeholder="Rechercher ou créer un tag..."
                  @keydown.enter.prevent="addTagFromSearch"
                  @keydown.escape="tagSearch = ''; showTagDropdown = false"
                  @focus="showTagDropdown = true"
                />
                <div
                  v-if="showTagDropdown && filteredTags.length"
                  class="absolute z-10 mt-1 w-full bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-md shadow-theme-lg max-h-32 overflow-y-auto"
                >
                  <button
                    v-for="tag in filteredTags"
                    :key="tag"
                    type="button"
                    class="w-full text-left px-3 py-1.5 text-sm hover:bg-gray-100 dark:hover:bg-white/5 text-gray-800 dark:text-gray-200"
                    @click="addTag(tag)"
                  >
                    {{ tag }}
                  </button>
                </div>
              </div>
            </div>

            <!-- Icon picker -->
            <IconPicker v-model="form.icon" />

            <!-- Tool prefix -->
            <div>
              <label for="form-tool-prefix" class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Préfixe d'outils
              </label>
              <input
                id="form-tool-prefix"
                v-model="form.tool_prefix"
                type="text"
                pattern="[a-zA-Z0-9]*"
                class="h-11 w-full rounded-lg border border-gray-300 bg-transparent px-4 py-2.5 text-sm text-gray-800 shadow-theme-xs placeholder:text-gray-400 focus:border-brand-300 focus:outline-hidden focus:ring-3 focus:ring-brand-500/10 dark:border-gray-700 dark:bg-gray-900 dark:text-white/90 dark:placeholder:text-white/30"
                placeholder="myprefix"
              />
              <p class="text-xs text-gray-400 dark:text-gray-500 mt-1">Alphanumérique uniquement</p>
            </div>

            <!-- Auto-discover -->
            <div class="flex items-center gap-2">
              <input
                id="form-discover"
                v-model="form.auto_discover"
                type="checkbox"
                class="rounded border-gray-300 text-brand-500 dark:border-gray-700"
              />
              <label for="form-discover" class="text-sm text-gray-700 dark:text-gray-300">
                Découvrir automatiquement les outils après création
              </label>
            </div>
          </div>

          <!-- Step 2: Vérification -->
          <div v-show="currentStep === 2" class="space-y-4">
            <h3 class="text-sm font-semibold text-gray-900 dark:text-white mb-3">Récapitulatif</h3>

            <dl class="divide-y divide-gray-100 dark:divide-gray-800">
              <!-- Template -->
              <div class="py-2 grid grid-cols-3 gap-4">
                <dt class="text-sm font-medium text-gray-500 dark:text-gray-400">Template</dt>
                <dd class="text-sm text-gray-900 dark:text-white col-span-2">{{ template.name }}</dd>
              </div>

              <!-- Name -->
              <div class="py-2 grid grid-cols-3 gap-4">
                <dt class="text-sm font-medium text-gray-500 dark:text-gray-400">Nom</dt>
                <dd class="text-sm text-gray-900 dark:text-white col-span-2">{{ form.name }}</dd>
              </div>

              <!-- Credentials -->
              <div class="py-2 grid grid-cols-3 gap-4">
                <dt class="text-sm font-medium text-gray-500 dark:text-gray-400">Compte de service</dt>
                <dd class="text-sm text-gray-900 dark:text-white col-span-2 font-mono text-xs break-all">
                  {{ fileInfo || (form.file ? form.file.name : '—') }}
                </dd>
              </div>

              <!-- Extra env -->
              <div
                v-if="template.required_extra_env && template.required_extra_env.length > 0"
                class="py-2 grid grid-cols-3 gap-4"
              >
                <dt class="text-sm font-medium text-gray-500 dark:text-gray-400">Variables env</dt>
                <dd class="text-sm text-gray-900 dark:text-white col-span-2">
                  <div
                    v-for="field in template.required_extra_env"
                    :key="field.key"
                    class="font-mono text-xs"
                  >
                    <span class="text-gray-500 dark:text-gray-400">{{ field.key }}</span> =
                    <span>{{ form.extra_env[field.key] || '—' }}</span>
                  </div>
                </dd>
              </div>

              <!-- Tags -->
              <div class="py-2 grid grid-cols-3 gap-4">
                <dt class="text-sm font-medium text-gray-500 dark:text-gray-400">Tags</dt>
                <dd class="text-sm text-gray-900 dark:text-white col-span-2">
                  <div v-if="form.tags.length" class="flex flex-wrap gap-1">
                    <span
                      v-for="tag in form.tags"
                      :key="tag"
                      class="inline-flex text-xs bg-brand-100 dark:bg-brand-500/20 text-brand-700 dark:text-brand-400 px-2 py-0.5 rounded-full"
                    >
                      {{ tag }}
                    </span>
                  </div>
                  <span v-else class="text-gray-400 dark:text-gray-500 italic">Aucun</span>
                </dd>
              </div>

              <!-- Icon -->
              <div v-if="form.icon" class="py-2 grid grid-cols-3 gap-4">
                <dt class="text-sm font-medium text-gray-500 dark:text-gray-400">Icone</dt>
                <dd class="col-span-2">
                  <img :src="form.icon" alt="Icon" class="w-8 h-8 rounded border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 object-contain p-0.5" />
                </dd>
              </div>

              <!-- Tool prefix -->
              <div v-if="form.tool_prefix" class="py-2 grid grid-cols-3 gap-4">
                <dt class="text-sm font-medium text-gray-500 dark:text-gray-400">Préfixe d'outils</dt>
                <dd class="text-sm text-gray-900 dark:text-white col-span-2 font-mono">{{ form.tool_prefix }}</dd>
              </div>

              <!-- Auto-discover -->
              <div class="py-2 grid grid-cols-3 gap-4">
                <dt class="text-sm font-medium text-gray-500 dark:text-gray-400">Auto-découverte</dt>
                <dd class="text-sm text-gray-900 dark:text-white col-span-2">{{ form.auto_discover ? 'Oui' : 'Non' }}</dd>
              </div>
            </dl>

            <!-- Submit error -->
            <div
              v-if="submitError"
              class="rounded-md bg-error-50 dark:bg-error-500/15 px-3 py-2 text-xs text-error-600 dark:text-error-400"
            >
              <i class="pi pi-exclamation-triangle text-[11px] mr-1" />
              {{ submitError }}
            </div>
          </div>
        </div>

        <!-- Step navigation -->
        <div class="flex justify-between mt-6">
          <button
            v-if="currentStep > 0"
            type="button"
            class="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-white/5 rounded-md hover:bg-gray-200 dark:hover:bg-gray-700"
            @click="goBack"
          >
            Précédent
          </button>
          <div v-else />

          <div class="flex gap-3">
            <button
              type="button"
              class="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-white/5 rounded-md hover:bg-gray-200 dark:hover:bg-gray-700"
              @click="router.push({ name: 'template-detail', params: { slug } })"
            >
              Annuler
            </button>
            <button
              v-if="currentStep < 2"
              type="button"
              class="px-4 py-2 text-sm font-medium text-white bg-brand-500 rounded-md hover:bg-brand-600 disabled:opacity-50"
              :disabled="!canGoNext"
              @click="goNext"
            >
              Suivant
            </button>
            <button
              v-if="currentStep === 2"
              type="button"
              class="px-4 py-2 text-sm font-medium text-white bg-brand-500 rounded-md hover:bg-brand-600 disabled:opacity-50"
              :disabled="submitting || !isStep0Valid || !isStep1Valid"
              @click="handleSubmit"
            >
              <i v-if="submitting" class="pi pi-spinner pi-spin mr-1" />
              Créer
            </button>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useTemplatesStore } from '@/stores/templates'
import { useServersStore } from '@/stores/servers'
import { useToast } from '@/composables/useToast'
import { templatesApi } from '@/api/templates'
import { ApiError } from '@/types/api'
import StepTabs from '@/components/shared/StepTabs.vue'
import IconPicker from '@/components/servers/IconPicker.vue'
import { validateSaJson } from '@/components/templates/validateSaJson'
import type { Template } from '@/types/templates'

const props = defineProps<{
  slug: string
}>()

const router = useRouter()
const store = useTemplatesStore()
const serversStore = useServersStore()
const toast = useToast()

const stepLabels = ['Informations de base', 'Tags et configuration', 'Vérification']
const currentStep = ref(0)
const loading = ref(false)
const submitting = ref(false)
const tagSearch = ref('')
const showTagDropdown = ref(false)
const fileInfo = ref('')
const fileError = ref('')
const submitError = ref('')

const template = ref<Template | null>(null)

const form = reactive<{
  name: string
  extra_env: Record<string, string>
  file: File | null
  tags: string[]
  icon: string
  tool_prefix: string
  auto_discover: boolean
}>({
  name: '',
  extra_env: {},
  file: null,
  tags: [],
  icon: '',
  tool_prefix: '',
  auto_discover: true
})

const toolPrefixValid = computed(() => {
  if (!form.tool_prefix) return true
  return /^[a-zA-Z0-9]*$/.test(form.tool_prefix)
})

const isStep0Valid = computed(() => {
  if (!form.name.trim()) return false
  if (!form.file) return false
  if (fileError.value) return false
  if (template.value?.required_extra_env) {
    for (const field of template.value.required_extra_env) {
      if (field.required) {
        const v = form.extra_env[field.key]
        if (!v || !v.trim()) return false
      }
    }
  }
  return true
})

const isStep1Valid = computed(() => toolPrefixValid.value)

const completedStepsArray = computed(() => {
  const completed: number[] = []
  if (isStep0Valid.value) completed.push(0)
  if (isStep0Valid.value && isStep1Valid.value) completed.push(1)
  return completed
})

const canGoNext = computed(() => {
  if (currentStep.value === 0) return isStep0Valid.value
  if (currentStep.value === 1) return isStep1Valid.value
  return false
})

const filteredTags = computed(() => {
  const q = tagSearch.value.toLowerCase()
  return serversStore.tags
    .filter(t => !form.tags.includes(t))
    .filter(t => !q || t.toLowerCase().includes(q))
})

onMounted(async () => {
  serversStore.fetchTags()

  loading.value = true
  try {
    template.value = await templatesApi.get(props.slug)
    // Pre-fill tool_prefix from template default
    if (template.value.tool_prefix && !form.tool_prefix) {
      form.tool_prefix = template.value.tool_prefix
    }
    // Pre-fill icon from template default
    if (template.value.icon && !form.icon) {
      form.icon = template.value.icon
    }
  } catch (err) {
    console.error('Failed to load template:', err)
    template.value = null
    toast.error('Impossible de charger le template')
  } finally {
    loading.value = false
  }
})

function goToStep(step: number) {
  if (step < currentStep.value || completedStepsArray.value.includes(step)) {
    currentStep.value = step
  }
}

function goNext() {
  if (canGoNext.value && currentStep.value < 2) {
    currentStep.value++
  }
}

function goBack() {
  if (currentStep.value > 0) {
    currentStep.value--
  }
}

function addTag(tag: string) {
  if (!form.tags.includes(tag)) {
    form.tags.push(tag)
  }
  tagSearch.value = ''
  showTagDropdown.value = false
}

function removeTag(tag: string) {
  form.tags = form.tags.filter(t => t !== tag)
}

function addTagFromSearch() {
  const tag = tagSearch.value.trim()
  if (tag && !form.tags.includes(tag)) {
    form.tags.push(tag)
  }
  tagSearch.value = ''
  showTagDropdown.value = false
}

async function onFile(e: Event): Promise<void> {
  const target = e.target as HTMLInputElement
  const f = target.files?.[0] ?? null
  form.file = f
  fileInfo.value = ''
  fileError.value = ''
  if (!f) return
  const result = await validateSaJson(f)
  if (!result.ok) {
    fileError.value = result.error ?? 'JSON invalide'
    return
  }
  fileInfo.value = result.clientEmail ?? ''
}

async function handleSubmit(): Promise<void> {
  if (!form.file || !template.value) return
  submitting.value = true
  submitError.value = ''
  try {
    const extraEnvCleaned: Record<string, string> = {}
    for (const [k, v] of Object.entries(form.extra_env)) {
      if (v && v.trim()) extraEnvCleaned[k] = v
    }
    await store.createInstance({
      template_slug: template.value.slug,
      name: form.name,
      extra_env: Object.keys(extraEnvCleaned).length ? extraEnvCleaned : undefined,
      credentials: form.file,
      tags: form.tags.length ? form.tags : undefined,
      icon: form.icon || undefined,
      tool_prefix: form.tool_prefix || undefined,
      auto_discover: form.auto_discover
    })
    toast.success('Instance créée')
    router.push({ name: 'template-detail', params: { slug: props.slug } })
  } catch (e: unknown) {
    if (e instanceof ApiError) {
      const body = e.body as { error?: string } | undefined
      submitError.value = body?.error ?? e.message
    } else if (e instanceof Error) {
      submitError.value = e.message
    } else {
      submitError.value = 'Échec de la création'
    }
    toast.error(submitError.value)
  } finally {
    submitting.value = false
  }
}
</script>
