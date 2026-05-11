<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import * as servicesApi from '@/api/services'
import StepTabs from '@/components/shared/StepTabs.vue'
import RedirectUriList from '@/components/services/RedirectUriList.vue'
import ClaimMapperEditor from '@/components/services/ClaimMapperEditor.vue'

const route = useRoute()
const router = useRouter()

const isEdit = computed(() => !!route.params.id)
const stepLabels = ['Identité', 'Configuration', 'Vérification']
const currentStep = ref(0)
const loading = ref(false)
const submitting = ref(false)
const error = ref('')

const issuedSecret = ref<string | null>(null)
const issuedClientId = ref<string | null>(null)

const form = reactive<{
  name: string
  description: string
  logo_url: string
  brand_color: string
  redirect_uris: string[]
  allowed_roles: string[]
  logout_webhook_url: string
  token_ttl_s: number
  refresh_ttl_s: number
  claim_mappings: Record<string, string>
}>({
  name: '',
  description: '',
  logo_url: '',
  brand_color: '#465fff',
  redirect_uris: [''],
  allowed_roles: [],
  logout_webhook_url: '',
  token_ttl_s: 60,
  refresh_ttl_s: 2592000,
  claim_mappings: {},
})

const roleSearch = ref('')

const isStep0Valid = computed(() => {
  if (!form.name.trim()) return false
  if (!form.redirect_uris.some((u) => u.trim())) return false
  return true
})

const completedSteps = computed(() => {
  const c: number[] = []
  if (isStep0Valid.value) c.push(0)
  if (isStep0Valid.value) c.push(1)
  return c
})

const canGoNext = computed(() => {
  if (currentStep.value === 0) return isStep0Valid.value
  if (currentStep.value === 1) return true
  return false
})

onMounted(async () => {
  if (!isEdit.value) return
  loading.value = true
  try {
    const c = await servicesApi.get(String(route.params.id))
    form.name = c.name
    form.description = c.description || ''
    form.logo_url = c.logo_url || ''
    form.brand_color = c.brand_color || '#465fff'
    form.redirect_uris = c.redirect_uris ?? ['']
    form.allowed_roles = c.allowed_roles ?? []
    form.logout_webhook_url = c.logout_webhook_url || ''
    form.token_ttl_s = c.token_ttl_s
    form.refresh_ttl_s = c.refresh_ttl_s
    form.claim_mappings = c.claim_mappings ?? {}
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Erreur de chargement'
  } finally {
    loading.value = false
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
  if (currentStep.value > 0) currentStep.value--
}

function addRole() {
  const r = roleSearch.value.trim()
  if (r && !form.allowed_roles.includes(r)) form.allowed_roles.push(r)
  roleSearch.value = ''
}
function removeRole(r: string) {
  form.allowed_roles = form.allowed_roles.filter((x) => x !== r)
}

async function submit() {
  submitting.value = true
  error.value = ''
  try {
    if (isEdit.value) {
      await servicesApi.update(String(route.params.id), form)
      router.push('/admin/services')
    } else {
      const r = await servicesApi.create(form)
      issuedClientId.value = r.client_id
      issuedSecret.value = r.client_secret
    }
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Erreur lors de l'enregistrement"
  } finally {
    submitting.value = false
  }
}

async function rotate() {
  if (!confirm("Régénérer le secret ? L'ancien sera invalidé immédiatement.")) return
  try {
    const r = await servicesApi.rotateSecret(String(route.params.id))
    issuedSecret.value = r.client_secret
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Erreur'
  }
}

async function testWebhook() {
  try {
    const r = await servicesApi.testWebhook(String(route.params.id))
    alert(`Webhook répondu: HTTP ${r.status}`)
  } catch (e) {
    alert('Webhook KO: ' + (e instanceof Error ? e.message : ''))
  }
}
</script>

<template>
  <div>
    <div class="mb-6 flex items-center gap-4">
      <button
        type="button"
        class="inline-flex items-center gap-1.5 text-sm text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white"
        @click="router.push('/admin/services')"
      >
        ← Retour
      </button>
      <h1 class="text-2xl font-bold text-gray-900 dark:text-white">
        {{ isEdit ? 'Modifier le service' : 'Nouveau service' }}
      </h1>
    </div>

    <div class="max-w-3xl mx-auto">
      <div v-if="loading" class="flex items-center justify-center py-20">
        <span class="text-2xl text-gray-400 dark:text-gray-500">⏳</span>
      </div>

      <template v-else>
        <div v-if="error" class="mb-4 p-3 bg-red-50 text-red-700 rounded">{{ error }}</div>

        <div
          v-if="issuedSecret"
          class="mb-6 p-4 bg-yellow-50 border border-yellow-300 rounded"
        >
          <p class="font-semibold text-yellow-800 mb-2">
            Secret généré — copier maintenant, il ne sera pas réaffiché
          </p>
          <p class="text-sm">
            client_id : <code class="font-mono">{{ issuedClientId }}</code>
          </p>
          <p class="text-sm break-all">
            client_secret : <code class="font-mono">{{ issuedSecret }}</code>
          </p>
          <button
            type="button"
            class="mt-2 px-3 py-1 bg-brand-500 text-white rounded"
            @click="router.push('/admin/services')"
          >
            OK
          </button>
        </div>

        <template v-else>
          <StepTabs
            v-if="!isEdit"
            :steps="stepLabels"
            :current-step="currentStep"
            :completed-steps="completedSteps"
            @update:current-step="goToStep"
          />

          <div
            class="bg-white dark:bg-gray-900 rounded-lg shadow-theme-xs border border-gray-200 dark:border-gray-800 p-6"
          >
            <!-- Step 0: Identité -->
            <div v-show="isEdit || currentStep === 0" class="space-y-4">
              <h3
                v-if="isEdit"
                class="text-sm font-semibold text-gray-900 dark:text-white mb-3"
              >
                Identité
              </h3>

              <div>
                <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Nom <span class="text-red-500">*</span>
                </label>
                <input
                  v-model="form.name"
                  type="text"
                  placeholder="api-gateway"
                  class="h-11 w-full rounded-lg border border-gray-300 bg-transparent px-4 py-2.5 text-sm text-gray-800 placeholder:text-gray-400 focus:border-brand-300 focus:outline-hidden focus:ring-3 focus:ring-brand-500/10 dark:border-gray-700 dark:bg-gray-900 dark:text-white/90"
                />
                <p class="text-xs text-gray-400 dark:text-gray-500 mt-1">
                  Doit correspondre à <code class="font-mono">SERVICE_NAME</code> sur le service consommateur.
                </p>
              </div>

              <div>
                <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Description
                </label>
                <textarea
                  v-model="form.description"
                  rows="2"
                  class="w-full rounded-lg border border-gray-300 bg-transparent px-4 py-2.5 text-sm text-gray-800 placeholder:text-gray-400 focus:border-brand-300 focus:outline-hidden focus:ring-3 focus:ring-brand-500/10 dark:border-gray-700 dark:bg-gray-900 dark:text-white/90"
                />
              </div>

              <div>
                <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  URIs de redirection <span class="text-red-500">*</span>
                </label>
                <RedirectUriList v-model="form.redirect_uris" />
                <p class="text-xs text-gray-400 dark:text-gray-500 mt-1">
                  Au moins une URI HTTPS (ou http://localhost) où le service recevra le code OAuth2.
                </p>
              </div>
            </div>

            <!-- Step 1: Configuration -->
            <div
              v-show="isEdit || currentStep === 1"
              :class="isEdit ? 'mt-6 pt-6 border-t border-gray-100 dark:border-gray-800' : ''"
              class="space-y-4"
            >
              <h3
                v-if="isEdit"
                class="text-sm font-semibold text-gray-900 dark:text-white mb-3"
              >
                Configuration
              </h3>

              <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    Logo URL
                  </label>
                  <input
                    v-model="form.logo_url"
                    type="url"
                    placeholder="/images/logos/service.svg"
                    class="h-11 w-full rounded-lg border border-gray-300 bg-transparent px-4 py-2.5 text-sm text-gray-800 placeholder:text-gray-400 focus:border-brand-300 focus:outline-hidden focus:ring-3 focus:ring-brand-500/10 dark:border-gray-700 dark:bg-gray-900 dark:text-white/90"
                  />
                </div>
                <div>
                  <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    Couleur de marque
                  </label>
                  <input
                    v-model="form.brand_color"
                    type="color"
                    class="h-11 w-full rounded-lg border border-gray-300 dark:border-gray-700"
                  />
                </div>
              </div>

              <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    TTL access token (s)
                  </label>
                  <input
                    v-model.number="form.token_ttl_s"
                    type="number"
                    min="30"
                    max="3600"
                    class="h-11 w-full rounded-lg border border-gray-300 bg-transparent px-4 py-2.5 text-sm text-gray-800 focus:border-brand-300 focus:outline-hidden focus:ring-3 focus:ring-brand-500/10 dark:border-gray-700 dark:bg-gray-900 dark:text-white/90"
                  />
                </div>
                <div>
                  <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    TTL refresh token (s)
                  </label>
                  <input
                    v-model.number="form.refresh_ttl_s"
                    type="number"
                    min="300"
                    max="7776000"
                    class="h-11 w-full rounded-lg border border-gray-300 bg-transparent px-4 py-2.5 text-sm text-gray-800 focus:border-brand-300 focus:outline-hidden focus:ring-3 focus:ring-brand-500/10 dark:border-gray-700 dark:bg-gray-900 dark:text-white/90"
                  />
                </div>
              </div>

              <div>
                <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Rôles autorisés
                </label>
                <div v-if="form.allowed_roles.length" class="flex flex-wrap gap-1 mb-2">
                  <span
                    v-for="r in form.allowed_roles"
                    :key="r"
                    class="inline-flex items-center gap-1 text-xs bg-brand-100 dark:bg-brand-500/20 text-brand-700 dark:text-brand-400 px-2 py-0.5 rounded-full"
                  >
                    {{ r }}
                    <button type="button" class="hover:text-brand-900" @click="removeRole(r)">×</button>
                  </span>
                </div>
                <input
                  v-model="roleSearch"
                  type="text"
                  placeholder="ajouter un rôle (Entrée pour valider)"
                  class="h-11 w-full rounded-lg border border-gray-300 bg-transparent px-4 py-2.5 text-sm text-gray-800 placeholder:text-gray-400 focus:border-brand-300 focus:outline-hidden focus:ring-3 focus:ring-brand-500/10 dark:border-gray-700 dark:bg-gray-900 dark:text-white/90"
                  @keydown.enter.prevent="addRole"
                />
                <p class="text-xs text-gray-400 dark:text-gray-500 mt-1">
                  Vide = tous les utilisateurs authentifiés peuvent SSO.
                </p>
              </div>

              <div>
                <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Webhook de déconnexion
                </label>
                <input
                  v-model="form.logout_webhook_url"
                  type="url"
                  placeholder="https://service.example/auth/logout-webhook"
                  class="h-11 w-full rounded-lg border border-gray-300 bg-transparent px-4 py-2.5 text-sm text-gray-800 placeholder:text-gray-400 focus:border-brand-300 focus:outline-hidden focus:ring-3 focus:ring-brand-500/10 dark:border-gray-700 dark:bg-gray-900 dark:text-white/90"
                />
                <button
                  v-if="isEdit"
                  type="button"
                  class="mt-2 text-sm text-brand-500 hover:underline"
                  @click="testWebhook"
                >
                  Tester le webhook
                </button>
              </div>

              <div>
                <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Mappings de claims
                </label>
                <ClaimMapperEditor v-model="form.claim_mappings" />
                <p class="text-xs text-gray-400 dark:text-gray-500 mt-1">
                  Vide = défauts <code class="font-mono">sub=email, name=display_name</code>.
                </p>
              </div>
            </div>

            <!-- Step 2: Récap (create only) -->
            <div v-if="!isEdit" v-show="currentStep === 2" class="space-y-4">
              <h3 class="text-sm font-semibold text-gray-900 dark:text-white mb-3">
                Récapitulatif
              </h3>
              <dl class="divide-y divide-gray-100 dark:divide-gray-800">
                <div class="py-2 grid grid-cols-3 gap-4">
                  <dt class="text-sm font-medium text-gray-500">Nom</dt>
                  <dd class="text-sm col-span-2">{{ form.name }}</dd>
                </div>
                <div v-if="form.description" class="py-2 grid grid-cols-3 gap-4">
                  <dt class="text-sm font-medium text-gray-500">Description</dt>
                  <dd class="text-sm col-span-2">{{ form.description }}</dd>
                </div>
                <div class="py-2 grid grid-cols-3 gap-4">
                  <dt class="text-sm font-medium text-gray-500">URIs de redirection</dt>
                  <dd class="text-sm col-span-2 font-mono whitespace-pre-line break-all">
                    {{ form.redirect_uris.filter((u) => u.trim()).join('\n') }}
                  </dd>
                </div>
                <div class="py-2 grid grid-cols-3 gap-4">
                  <dt class="text-sm font-medium text-gray-500">TTL access / refresh</dt>
                  <dd class="text-sm col-span-2">
                    {{ form.token_ttl_s }}s / {{ form.refresh_ttl_s }}s
                  </dd>
                </div>
                <div v-if="form.allowed_roles.length" class="py-2 grid grid-cols-3 gap-4">
                  <dt class="text-sm font-medium text-gray-500">Rôles autorisés</dt>
                  <dd class="text-sm col-span-2">{{ form.allowed_roles.join(', ') }}</dd>
                </div>
                <div v-if="form.logout_webhook_url" class="py-2 grid grid-cols-3 gap-4">
                  <dt class="text-sm font-medium text-gray-500">Webhook logout</dt>
                  <dd class="text-sm col-span-2 font-mono text-xs break-all">
                    {{ form.logout_webhook_url }}
                  </dd>
                </div>
                <div v-if="Object.keys(form.claim_mappings).length" class="py-2 grid grid-cols-3 gap-4">
                  <dt class="text-sm font-medium text-gray-500">Mappings de claims</dt>
                  <dd class="text-sm col-span-2 font-mono text-xs whitespace-pre">
                    {{ JSON.stringify(form.claim_mappings, null, 2) }}
                  </dd>
                </div>
              </dl>
            </div>
          </div>

          <!-- Edit: single submit -->
          <div v-if="isEdit" class="flex justify-end gap-3 mt-6">
            <button
              type="button"
              class="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-white/5 rounded-md hover:bg-gray-200 dark:hover:bg-gray-700"
              @click="router.push('/admin/services')"
            >
              Annuler
            </button>
            <button
              type="button"
              class="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-white/5 rounded-md hover:bg-gray-200 dark:hover:bg-gray-700"
              @click="rotate"
            >
              Régénérer le secret
            </button>
            <button
              type="button"
              class="px-4 py-2 text-sm font-medium text-white bg-brand-500 rounded-md hover:bg-brand-600 disabled:opacity-50"
              :disabled="submitting || !isStep0Valid"
              @click="submit"
            >
              {{ submitting ? 'Enregistrement…' : 'Enregistrer' }}
            </button>
          </div>

          <!-- Create: stepped nav -->
          <div v-else class="flex justify-between mt-6">
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
                @click="router.push('/admin/services')"
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
                :disabled="submitting"
                @click="submit"
              >
                {{ submitting ? 'Création…' : 'Créer' }}
              </button>
            </div>
          </div>
        </template>
      </template>
    </div>
  </div>
</template>
