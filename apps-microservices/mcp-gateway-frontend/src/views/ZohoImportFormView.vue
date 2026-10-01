<template>
  <div>
    <div class="mb-6 flex items-center gap-4">
      <BaseButton variant="ghost" size="sm" @click="goBack">
        <i class="pi pi-arrow-left text-xs mr-1" />
        Retour
      </BaseButton>
      <h1 class="text-2xl font-bold text-gray-900 dark:text-white">
        {{ pageTitle }}
      </h1>
    </div>

    <div class="max-w-3xl mx-auto">
      <StepTabs
        :steps="stepLabels"
        :current-step="currentStep"
        :completed-steps="completedSteps"
        @update:current-step="goToStep"
      />

      <div class="bg-white dark:bg-gray-900 rounded-lg shadow-theme-xs border border-gray-200 dark:border-gray-800 p-6">
        <!-- Step 0: Identité -->
        <div v-show="currentStep === 0" class="space-y-4">
          <div
            v-if="scope === 'admin' && hasExistingAdmin"
            class="rounded-md bg-warning-50 dark:bg-warning-500/15 px-3 py-2 text-xs text-warning-700 dark:text-warning-400"
          >
            Un compte admin existe déjà — la création remplacera la configuration actuelle.
          </div>

          <FormField label="Nom" required>
            <template #default="{ id }">
              <BaseInput :id="id" v-model="form.name" placeholder="ex: Compte admin Zoho" />
            </template>
          </FormField>

          <FormField v-if="scope === 'users'" label="Créé par (email)" required>
            <template #default="{ id }">
              <BaseInput :id="id" v-model="form.created_by" type="email" placeholder="user@hellopro.fr" />
            </template>
          </FormField>
        </div>

        <!-- Step 1: Endpoint -->
        <div v-show="currentStep === 1" class="space-y-4">
          <FormField label="URL upstream" required>
            <template #default="{ id }">
              <BaseInput :id="id" v-model="form.url" type="url" placeholder="https://mcp-zoho.example.com" />
            </template>
          </FormField>

          <FormField label="Auth headers (JSON)" :error="authHeadersError">
            <template #default="{ id }">
              <BaseTextarea
                :id="id"
                v-model="form.authHeadersJson"
                :rows="4"
                monospace
                placeholder='{"Authorization": "Bearer xxx"}'
              />
            </template>
          </FormField>

          <div v-if="scope === 'users'" class="flex items-center gap-2">
            <input
              id="zoho-form-active"
              v-model="form.is_active"
              type="checkbox"
              class="rounded border-gray-300 text-brand-500 dark:border-gray-700"
            />
            <label for="zoho-form-active" class="text-sm text-gray-700 dark:text-gray-300">
              Import actif
            </label>
          </div>
        </div>

        <!-- Step 2: Récapitulatif -->
        <div v-show="currentStep === 2" class="space-y-4">
          <h3 class="text-sm font-semibold text-gray-900 dark:text-white mb-3">Récapitulatif</h3>
          <dl class="divide-y divide-gray-100 dark:divide-gray-800">
            <div class="py-2 grid grid-cols-3 gap-4">
              <dt class="text-sm font-medium text-gray-500 dark:text-gray-400">Type</dt>
              <dd class="text-sm text-gray-900 dark:text-white col-span-2">
                {{ scope === 'admin' ? 'Compte admin (singleton)' : 'Import utilisateur' }}
              </dd>
            </div>
            <div class="py-2 grid grid-cols-3 gap-4">
              <dt class="text-sm font-medium text-gray-500 dark:text-gray-400">Nom</dt>
              <dd class="text-sm text-gray-900 dark:text-white col-span-2">{{ form.name }}</dd>
            </div>
            <div v-if="scope === 'users'" class="py-2 grid grid-cols-3 gap-4">
              <dt class="text-sm font-medium text-gray-500 dark:text-gray-400">Créé par</dt>
              <dd class="text-sm text-gray-900 dark:text-white col-span-2">{{ form.created_by }}</dd>
            </div>
            <div class="py-2 grid grid-cols-3 gap-4">
              <dt class="text-sm font-medium text-gray-500 dark:text-gray-400">URL</dt>
              <dd class="text-sm text-gray-900 dark:text-white col-span-2 break-all">{{ form.url }}</dd>
            </div>
            <div v-if="authHeaderKeys.length" class="py-2 grid grid-cols-3 gap-4">
              <dt class="text-sm font-medium text-gray-500 dark:text-gray-400">En-têtes auth</dt>
              <dd class="text-sm text-gray-900 dark:text-white col-span-2 font-mono text-xs">
                <span v-for="k in authHeaderKeys" :key="k" class="mr-2">{{ k }}</span>
              </dd>
            </div>
            <div v-if="scope === 'users'" class="py-2 grid grid-cols-3 gap-4">
              <dt class="text-sm font-medium text-gray-500 dark:text-gray-400">Actif</dt>
              <dd class="text-sm text-gray-900 dark:text-white col-span-2">{{ form.is_active ? 'Oui' : 'Non' }}</dd>
            </div>
          </dl>
        </div>
      </div>

      <div class="flex justify-between mt-6">
        <BaseButton v-if="currentStep > 0" variant="secondary" @click="currentStep--">Précédent</BaseButton>
        <div v-else />
        <div class="flex gap-3">
          <BaseButton variant="secondary" @click="goBack">Annuler</BaseButton>
          <BaseButton v-if="currentStep < 2" :disabled="!canGoNext" @click="goNext">Suivant</BaseButton>
          <BaseButton v-if="currentStep === 2" :loading="submitting" @click="handleSubmit">Créer</BaseButton>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useZohoImportsStore } from '@/stores/zohoImports'
import { useToast } from '@/composables/useToast'
import StepTabs from '@/components/shared/StepTabs.vue'
import BaseInput from '@/components/ui/BaseInput.vue'
import BaseTextarea from '@/components/ui/BaseTextarea.vue'
import BaseButton from '@/components/ui/BaseButton.vue'
import FormField from '@/components/ui/FormField.vue'
import { toErrorMessage } from '@/utils/error'

const props = defineProps<{ slug: string }>()

const route = useRoute()
const router = useRouter()
const store = useZohoImportsStore()
const toast = useToast()

const stepLabels = ['Identité', 'Endpoint', 'Récapitulatif']
const currentStep = ref(0)
const submitting = ref(false)
const authHeadersError = ref('')

const scope = computed<'admin' | 'users'>(() => {
  const q = route.query.scope
  return q === 'admin' ? 'admin' : 'users'
})

const pageTitle = computed(() =>
  scope.value === 'admin' ? 'Nouveau compte admin Zoho' : 'Nouvel import Zoho'
)

const hasExistingAdmin = computed(() => store.admin !== null)

const form = reactive({
  name: '',
  url: '',
  authHeadersJson: '',
  created_by: '',
  is_active: true,
})

const authHeaderKeys = computed<string[]>(() => {
  if (!form.authHeadersJson.trim()) return []
  try {
    const parsed = JSON.parse(form.authHeadersJson)
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
      return Object.keys(parsed)
    }
  } catch {
    return []
  }
  return []
})

const isStep0Valid = computed(() => {
  if (!form.name.trim()) return false
  if (scope.value === 'users') {
    if (!form.created_by.trim() || !form.created_by.includes('@')) return false
  }
  return true
})

const isStep1Valid = computed(() => {
  if (!form.url.trim()) return false
  if (form.authHeadersJson.trim()) {
    try {
      const parsed = JSON.parse(form.authHeadersJson)
      if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
        return false
      }
    } catch {
      return false
    }
  }
  return true
})

watch(
  () => form.authHeadersJson,
  (raw) => {
    if (!raw.trim()) {
      authHeadersError.value = ''
      return
    }
    try {
      const parsed = JSON.parse(raw)
      if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
        authHeadersError.value = 'Doit être un objet JSON {"clé":"valeur"}.'
        return
      }
      authHeadersError.value = ''
    } catch {
      authHeadersError.value = 'JSON invalide.'
    }
  }
)

const canGoNext = computed(() => {
  if (currentStep.value === 0) return isStep0Valid.value
  if (currentStep.value === 1) return isStep1Valid.value
  return false
})

const completedSteps = computed(() => {
  const out: number[] = []
  if (isStep0Valid.value) out.push(0)
  if (isStep0Valid.value && isStep1Valid.value) out.push(1)
  return out
})

onMounted(() => {
  if (scope.value === 'admin' && !store.admin) {
    store.fetchAdmin()
  }
})

function goToStep(step: number) {
  if (step < currentStep.value || completedSteps.value.includes(step)) {
    currentStep.value = step
  }
}

function goNext() {
  if (canGoNext.value && currentStep.value < 2) currentStep.value++
}

function goBack() {
  router.push({ name: 'template-detail', params: { slug: props.slug } })
}

function parseAuthHeaders(): Record<string, string> | undefined {
  const raw = form.authHeadersJson.trim()
  if (!raw) return undefined
  try {
    const parsed = JSON.parse(raw)
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
      return parsed as Record<string, string>
    }
    authHeadersError.value = 'Doit être un objet JSON {"clé":"valeur"}.'
    return undefined
  } catch {
    authHeadersError.value = 'JSON invalide.'
    return undefined
  }
}

async function handleSubmit() {
  submitting.value = true
  try {
    const authHeaders = parseAuthHeaders()
    if (authHeadersError.value) return

    if (scope.value === 'admin') {
      await store.upsertAdmin({
        name: form.name.trim(),
        url: form.url.trim(),
        auth_headers: authHeaders,
      })
    } else {
      await store.createUserImport({
        name: form.name.trim(),
        url: form.url.trim(),
        created_by: form.created_by.trim(),
        auth_headers: authHeaders,
        is_active: form.is_active,
        template_slug: props.slug,
      })
    }
    toast.success(scope.value === 'admin' ? 'Compte admin créé' : 'Import créé')
    router.push({
      name: 'template-detail',
      params: { slug: props.slug },
      query: { zoho_tab: scope.value },
    })
  } catch (err) {
    toast.error(toErrorMessage(err, "Erreur lors de la création"))
  } finally {
    submitting.value = false
  }
}
</script>
