<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import * as apiCatalog from '@/api/apiCatalog'
import type { Protocol, Status } from '@/types/apiCatalog'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const isEdit = computed(() => !!route.params.id)
const loading = ref(false)
const submitting = ref(false)
const error = ref('')

// Source of the loaded service (only relevant in edit mode)
const serviceSource = ref<string>('manual')

const form = reactive<{
  name: string
  baseUrl: string
  protocols: Protocol[]
  description: string
  owner: string
  tagsInput: string
  apiInfoUrl: string
  grpcAddress: string
  status: Status
}>({
  name: '',
  baseUrl: '',
  protocols: ['rest'],
  description: '',
  owner: '',
  tagsInput: '',
  apiInfoUrl: '',
  grpcAddress: '',
  status: 'active',
})

// In edit mode, identity fields (name, baseUrl, protocols, apiInfoUrl, grpcAddress)
// are editable only when source === 'manual'. name is always locked in edit mode.
const identityLocked = computed(() => isEdit.value && serviceSource.value !== 'manual')

const parsedTags = computed(() =>
  form.tagsInput
    .split(',')
    .map((t) => t.trim())
    .filter(Boolean),
)

const isValid = computed(() => {
  if (!form.name.trim()) return false
  if (!form.baseUrl.trim()) return false
  if (!form.protocols.length) return false
  return true
})

function toggleProtocol(p: Protocol) {
  const idx = form.protocols.indexOf(p)
  if (idx >= 0) {
    form.protocols.splice(idx, 1)
  } else {
    form.protocols.push(p)
  }
}

onMounted(async () => {
  if (!isEdit.value) return
  loading.value = true
  try {
    const r = await apiCatalog.get(String(route.params.id))
    const s = r.service
    serviceSource.value = s.source
    form.name = s.name
    form.baseUrl = s.baseUrl
    form.protocols = [...s.protocols]
    form.description = s.description || ''
    form.owner = s.owner || ''
    form.tagsInput = (s.tags || []).join(', ')
    form.apiInfoUrl = s.apiInfoUrl || ''
    form.grpcAddress = s.grpcAddress || ''
    form.status = s.status
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Erreur de chargement'
  } finally {
    loading.value = false
  }
})

async function submit() {
  submitting.value = true
  error.value = ''
  try {
    if (isEdit.value) {
      await apiCatalog.update(String(route.params.id), {
        description: form.description || undefined,
        owner: form.owner || undefined,
        tags: parsedTags.value.length ? parsedTags.value : undefined,
        status: auth.isAdmin ? form.status : undefined,
      })
    } else {
      await apiCatalog.create({
        name: form.name,
        baseUrl: form.baseUrl,
        protocols: form.protocols,
        description: form.description || undefined,
        owner: form.owner || undefined,
        tags: parsedTags.value.length ? parsedTags.value : undefined,
        apiInfoUrl: form.apiInfoUrl || undefined,
        grpcAddress: form.grpcAddress || undefined,
      })
    }
    router.push('/admin/api')
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Erreur lors de l'enregistrement"
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div>
    <div class="mb-6 flex items-center gap-4">
      <button
        type="button"
        class="inline-flex items-center gap-1.5 text-sm text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white"
        @click="router.back()"
      >
        ← Retour
      </button>
      <h1 class="text-2xl font-bold text-gray-900 dark:text-white">
        {{ isEdit ? 'Modifier le service API' : 'Nouveau service API' }}
      </h1>
    </div>

    <div class="max-w-2xl mx-auto">
      <div v-if="loading" class="flex items-center justify-center py-20">
        <span class="text-2xl text-gray-400">⏳</span>
      </div>

      <template v-else>
        <div v-if="error" class="mb-4 p-3 bg-red-50 text-red-700 rounded">{{ error }}</div>

        <div class="bg-white dark:bg-gray-900 rounded-lg shadow-theme-xs border border-gray-200 dark:border-gray-800 p-6 space-y-5">
          <!-- Identity fields (locked in edit or when source != manual) -->
          <div>
            <h3 class="text-sm font-semibold text-gray-900 dark:text-white mb-3">Identité</h3>

            <div v-if="identityLocked" class="mb-3 p-3 bg-gray-50 dark:bg-gray-800 rounded text-xs text-gray-500">
              Champs gérés par le scan automatique — modification désactivée.
            </div>

            <div class="space-y-4">
              <div>
                <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Nom <span class="text-red-500">*</span>
                </label>
                <input
                  v-model="form.name"
                  type="text"
                  placeholder="mon-service-api"
                  :disabled="isEdit"
                  class="h-11 w-full rounded-lg border border-gray-300 bg-transparent px-4 py-2.5 text-sm text-gray-800 placeholder:text-gray-400 focus:border-brand-300 focus:outline-hidden focus:ring-3 focus:ring-brand-500/10 dark:border-gray-700 dark:bg-gray-900 dark:text-white/90 disabled:opacity-60 disabled:cursor-not-allowed"
                />
                <p v-if="isEdit" class="text-xs text-gray-400 mt-1">Le nom est un identifiant immuable.</p>
              </div>

              <div>
                <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  URL de base <span class="text-red-500">*</span>
                </label>
                <input
                  v-model="form.baseUrl"
                  type="url"
                  placeholder="http://mon-service:8000"
                  :disabled="identityLocked"
                  class="h-11 w-full rounded-lg border border-gray-300 bg-transparent px-4 py-2.5 text-sm text-gray-800 placeholder:text-gray-400 focus:border-brand-300 focus:outline-hidden focus:ring-3 focus:ring-brand-500/10 dark:border-gray-700 dark:bg-gray-900 dark:text-white/90 disabled:opacity-60 disabled:cursor-not-allowed"
                />
              </div>

              <div>
                <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Protocoles <span class="text-red-500">*</span>
                </label>
                <div class="flex gap-4">
                  <label
                    v-for="p in (['rest', 'ws', 'grpc'] as Protocol[])"
                    :key="p"
                    class="flex items-center gap-2 text-sm cursor-pointer"
                    :class="identityLocked ? 'opacity-60 cursor-not-allowed' : ''"
                  >
                    <input
                      type="checkbox"
                      :checked="form.protocols.includes(p)"
                      :disabled="identityLocked"
                      class="rounded"
                      @change="!identityLocked && toggleProtocol(p)"
                    />
                    {{ p === 'rest' ? 'REST' : p === 'ws' ? 'WebSocket' : 'gRPC' }}
                  </label>
                </div>
              </div>

              <div>
                <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  URL OpenAPI / AsyncAPI
                </label>
                <input
                  v-model="form.apiInfoUrl"
                  type="url"
                  placeholder="http://mon-service:8000/openapi.json"
                  :disabled="identityLocked"
                  class="h-11 w-full rounded-lg border border-gray-300 bg-transparent px-4 py-2.5 text-sm text-gray-800 placeholder:text-gray-400 focus:border-brand-300 focus:outline-hidden focus:ring-3 focus:ring-brand-500/10 dark:border-gray-700 dark:bg-gray-900 dark:text-white/90 disabled:opacity-60 disabled:cursor-not-allowed"
                />
              </div>

              <div>
                <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Adresse gRPC
                </label>
                <input
                  v-model="form.grpcAddress"
                  type="text"
                  placeholder="mon-service:50051"
                  :disabled="identityLocked"
                  class="h-11 w-full rounded-lg border border-gray-300 bg-transparent px-4 py-2.5 text-sm text-gray-800 placeholder:text-gray-400 focus:border-brand-300 focus:outline-hidden focus:ring-3 focus:ring-brand-500/10 dark:border-gray-700 dark:bg-gray-900 dark:text-white/90 disabled:opacity-60 disabled:cursor-not-allowed"
                />
              </div>
            </div>
          </div>

          <!-- Editable fields (always) -->
          <div class="pt-4 border-t border-gray-100 dark:border-gray-800 space-y-4">
            <h3 class="text-sm font-semibold text-gray-900 dark:text-white mb-3">Description & organisation</h3>

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
                Propriétaire
              </label>
              <input
                v-model="form.owner"
                type="text"
                placeholder="equipe-data"
                class="h-11 w-full rounded-lg border border-gray-300 bg-transparent px-4 py-2.5 text-sm text-gray-800 placeholder:text-gray-400 focus:border-brand-300 focus:outline-hidden focus:ring-3 focus:ring-brand-500/10 dark:border-gray-700 dark:bg-gray-900 dark:text-white/90"
              />
            </div>

            <div>
              <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Tags <span class="text-xs text-gray-400">(séparés par des virgules)</span>
              </label>
              <input
                v-model="form.tagsInput"
                type="text"
                placeholder="rag, embedding, grpc"
                class="h-11 w-full rounded-lg border border-gray-300 bg-transparent px-4 py-2.5 text-sm text-gray-800 placeholder:text-gray-400 focus:border-brand-300 focus:outline-hidden focus:ring-3 focus:ring-brand-500/10 dark:border-gray-700 dark:bg-gray-900 dark:text-white/90"
              />
            </div>

            <!-- Status: admin only -->
            <div v-if="auth.isAdmin && isEdit">
              <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Statut
              </label>
              <select
                v-model="form.status"
                class="h-11 w-full rounded-lg border border-gray-300 bg-transparent px-4 text-sm text-gray-800 focus:border-brand-300 focus:outline-hidden focus:ring-3 focus:ring-brand-500/10 dark:border-gray-700 dark:bg-gray-900 dark:text-white/90"
              >
                <option value="active">Actif</option>
                <option value="deprecated">Déprécié</option>
                <option value="down">Hors ligne</option>
              </select>
            </div>
          </div>
        </div>

        <!-- Actions -->
        <div class="flex justify-end gap-3 mt-6">
          <button
            type="button"
            class="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-white/5 rounded-md hover:bg-gray-200 dark:hover:bg-gray-700"
            @click="router.back()"
          >
            Annuler
          </button>
          <button
            type="button"
            class="px-4 py-2 text-sm font-medium text-white bg-brand-500 rounded-md hover:bg-brand-600 disabled:opacity-50"
            :disabled="submitting || !isValid"
            @click="submit"
          >
            {{ submitting ? (isEdit ? 'Enregistrement…' : 'Création…') : (isEdit ? 'Enregistrer' : 'Créer') }}
          </button>
        </div>
      </template>
    </div>
  </div>
</template>
