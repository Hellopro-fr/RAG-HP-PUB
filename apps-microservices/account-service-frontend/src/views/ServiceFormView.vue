<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import * as servicesApi from '@/api/services'
import type { OAuth2ClientCreatePayload } from '@/types/oauth2'
import RedirectUriList from '@/components/services/RedirectUriList.vue'
import ClaimMapperEditor from '@/components/services/ClaimMapperEditor.vue'

const route = useRoute()
const router = useRouter()
const isEdit = !!route.params.id

const form = ref<OAuth2ClientCreatePayload>({
  name: '',
  redirect_uris: [''],
  token_ttl_s: 60,
  refresh_ttl_s: 2592000,
  allowed_roles: [],
  claim_mappings: {},
})
const error = ref('')
const saving = ref(false)
const issuedSecret = ref<string | null>(null)
const issuedClientId = ref<string | null>(null)

onMounted(async () => {
  if (!isEdit) return
  try {
    const c = await servicesApi.get(String(route.params.id))
    form.value = {
      name: c.name,
      description: c.description,
      logo_url: c.logo_url,
      brand_color: c.brand_color,
      redirect_uris: c.redirect_uris ?? [''],
      allowed_roles: c.allowed_roles ?? [],
      logout_webhook_url: c.logout_webhook_url,
      token_ttl_s: c.token_ttl_s,
      refresh_ttl_s: c.refresh_ttl_s,
      claim_mappings: c.claim_mappings ?? {},
      scope: c.scope,
    }
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Erreur de chargement'
  }
})

async function save() {
  saving.value = true
  error.value = ''
  try {
    if (isEdit) {
      await servicesApi.update(String(route.params.id), form.value)
      router.push('/admin/services')
    } else {
      const r = await servicesApi.create(form.value)
      issuedClientId.value = r.client_id
      issuedSecret.value = r.client_secret
    }
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Erreur'
  } finally {
    saving.value = false
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
  <div class="p-6 max-w-3xl">
    <h1 class="text-2xl font-semibold mb-4">
      {{ isEdit ? 'Modifier un service' : 'Nouveau service' }}
    </h1>

    <div v-if="error" class="mb-4 p-3 bg-red-50 text-red-700 rounded">{{ error }}</div>

    <div v-if="issuedSecret" class="mb-6 p-4 bg-yellow-50 border border-yellow-300 rounded">
      <p class="font-semibold text-yellow-800 mb-2">Secret généré — copier maintenant, il ne sera pas réaffiché</p>
      <p class="text-sm">client_id: <code class="font-mono">{{ issuedClientId }}</code></p>
      <p class="text-sm">client_secret: <code class="font-mono break-all">{{ issuedSecret }}</code></p>
      <button class="mt-2 px-3 py-1 bg-blue-600 text-white rounded" @click="router.push('/admin/services')">OK</button>
    </div>

    <form v-else @submit.prevent="save" class="space-y-6">
      <fieldset class="bg-white dark:bg-gray-900 p-4 rounded shadow">
        <legend class="font-semibold">Identité</legend>
        <label class="block text-sm mb-1 mt-2">Nom</label>
        <input v-model="form.name" required class="w-full h-10 px-3 border rounded dark:bg-gray-900 dark:border-gray-700" />
        <label class="block text-sm mb-1 mt-3">Description</label>
        <textarea v-model="form.description" class="w-full h-20 px-3 py-2 border rounded dark:bg-gray-900 dark:border-gray-700" />
      </fieldset>

      <fieldset class="bg-white dark:bg-gray-900 p-4 rounded shadow">
        <legend class="font-semibold">Branding</legend>
        <label class="block text-sm mb-1 mt-2">Logo URL</label>
        <input v-model="form.logo_url" class="w-full h-10 px-3 border rounded dark:bg-gray-900 dark:border-gray-700" />
        <label class="block text-sm mb-1 mt-3">Couleur</label>
        <input v-model="form.brand_color" type="color" class="h-10 w-20 border rounded" />
      </fieldset>

      <fieldset class="bg-white dark:bg-gray-900 p-4 rounded shadow">
        <legend class="font-semibold">URIs de redirection</legend>
        <RedirectUriList v-model="form.redirect_uris" />
      </fieldset>

      <fieldset class="bg-white dark:bg-gray-900 p-4 rounded shadow">
        <legend class="font-semibold">Politique de jetons</legend>
        <label class="block text-sm mb-1 mt-2">TTL access (s)</label>
        <input v-model.number="form.token_ttl_s" type="number" min="30" max="3600" class="h-10 px-3 border rounded dark:bg-gray-900 dark:border-gray-700" />
        <label class="block text-sm mb-1 mt-3">TTL refresh (s)</label>
        <input v-model.number="form.refresh_ttl_s" type="number" min="300" max="7776000" class="h-10 px-3 border rounded dark:bg-gray-900 dark:border-gray-700" />
      </fieldset>

      <fieldset class="bg-white dark:bg-gray-900 p-4 rounded shadow">
        <legend class="font-semibold">Webhook de déconnexion</legend>
        <input
          v-model="form.logout_webhook_url"
          type="url"
          placeholder="https://service/back-channel-logout"
          class="w-full h-10 px-3 border rounded dark:bg-gray-900 dark:border-gray-700"
        />
        <button v-if="isEdit" type="button" class="mt-2 text-sm text-blue-600" @click="testWebhook">
          Tester le webhook
        </button>
      </fieldset>

      <fieldset class="bg-white dark:bg-gray-900 p-4 rounded shadow">
        <legend class="font-semibold">Mappings de claims</legend>
        <ClaimMapperEditor v-model="form.claim_mappings!" />
      </fieldset>

      <div class="flex gap-2">
        <button type="submit" :disabled="saving" class="px-4 py-2 bg-blue-600 text-white rounded">
          {{ saving ? 'Enregistrement…' : (isEdit ? 'Mettre à jour' : 'Créer') }}
        </button>
        <button v-if="isEdit" type="button" @click="rotate" class="px-4 py-2 border rounded">
          Régénérer le secret
        </button>
        <button type="button" @click="router.push('/admin/services')" class="px-4 py-2 border rounded">
          Annuler
        </button>
      </div>
    </form>
  </div>
</template>
