<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { ApiError } from '@/api/client'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const username = ref('')
const password = ref('')
const errorMessage = ref('')

const oauthMode = computed(() =>
  Boolean(route.query.client_id && route.query.redirect_uri && route.query.code_challenge),
)

interface Branding {
  name?: string
  logo_url?: string
  brand_color?: string
}
const branding = ref<Branding | null>(null)

onMounted(async () => {
  if (!oauthMode.value) return
  try {
    const cid = String(route.query.client_id)
    const res = await fetch(`/authorize/branding/${cid}`)
    if (res.ok) branding.value = await res.json()
  } catch {
    /* ignore: fallback to default branding */
  }
})

async function handleAdminLogin() {
  errorMessage.value = ''
  try {
    await auth.login(username.value, password.value)
    const redirect = (route.query.redirect as string) || (auth.isAdmin ? '/admin/services' : '/me')
    router.push(redirect)
  } catch (e) {
    errorMessage.value = e instanceof ApiError ? e.message : 'Erreur de connexion'
  }
}

function ensureFilled(e: Event) {
  if (!username.value || !password.value) {
    e.preventDefault()
    errorMessage.value = 'Tous les champs sont obligatoires'
  }
}
</script>

<template>
  <div class="min-h-screen flex">
    <div class="hidden lg:flex lg:w-1/2 bg-[#1C2434] relative items-center justify-center px-12">
      <div class="relative z-10 text-center max-w-md">
        <div
          v-if="branding?.logo_url"
          class="mx-auto mb-8 w-20 h-20 rounded-2xl bg-white flex items-center justify-center p-3 shadow-lg"
        >
          <img :src="branding.logo_url" :alt="branding.name ?? 'Service'" class="w-full h-full object-contain" />
        </div>
        <h1 class="text-3xl font-bold text-white mb-4">
          {{ oauthMode ? `Connexion à ${branding?.name ?? 'votre service'}` : 'Account Service' }}
        </h1>
        <p class="text-gray-400 text-base leading-relaxed">
          Plateforme d'identité unifiée Hellopro.
        </p>
      </div>
    </div>

    <div class="w-full lg:w-1/2 flex items-center justify-center bg-gray-100 dark:bg-gray-950 px-6">
      <div class="w-full max-w-sm">
        <div class="bg-white dark:bg-gray-900 rounded-lg shadow-md p-8">
          <h2 class="text-xl font-semibold text-gray-900 dark:text-white mb-1">Connexion</h2>
          <p class="text-sm text-gray-500 dark:text-gray-400 mb-6">
            {{ oauthMode ? 'Authentifiez-vous pour accéder à ce service.' : 'Accédez au tableau de bord.' }}
          </p>

          <div
            v-if="errorMessage"
            class="mb-4 p-3 bg-red-50 border border-red-200 rounded-md text-sm text-red-700 dark:bg-red-900/20 dark:border-red-800 dark:text-red-300"
          >
            {{ errorMessage }}
          </div>

          <!-- OAuth2 mode: real form POST /authorize -->
          <form
            v-if="oauthMode"
            action="/authorize"
            method="POST"
            enctype="application/x-www-form-urlencoded"
            @submit="ensureFilled"
          >
            <input type="hidden" name="action" value="login" />
            <input type="hidden" name="response_type" :value="route.query.response_type" />
            <input type="hidden" name="client_id" :value="route.query.client_id" />
            <input type="hidden" name="redirect_uri" :value="route.query.redirect_uri" />
            <input type="hidden" name="code_challenge" :value="route.query.code_challenge" />
            <input type="hidden" name="code_challenge_method" value="S256" />
            <input type="hidden" name="state" :value="route.query.state ?? ''" />
            <div class="mb-4">
              <label for="u-oauth" class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Nom d'utilisateur</label>
              <input id="u-oauth" name="username" v-model="username" type="text" required class="h-11 w-full rounded-lg border border-gray-300 px-3 dark:border-gray-700 dark:bg-gray-900 dark:text-white" />
            </div>
            <div class="mb-6">
              <label for="p-oauth" class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Mot de passe</label>
              <input id="p-oauth" name="password" v-model="password" type="password" required class="h-11 w-full rounded-lg border border-gray-300 px-3 dark:border-gray-700 dark:bg-gray-900 dark:text-white" />
            </div>
            <button type="submit" class="w-full py-2.5 px-4 bg-blue-600 text-white font-medium rounded-md hover:bg-blue-700">
              Se connecter
            </button>
          </form>

          <!-- Admin UI mode: JS-driven JSON POST /api/v1/login -->
          <form v-else @submit.prevent="handleAdminLogin">
            <div class="mb-4">
              <label for="u-admin" class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Nom d'utilisateur</label>
              <input id="u-admin" v-model="username" type="text" required class="h-11 w-full rounded-lg border border-gray-300 px-3 dark:border-gray-700 dark:bg-gray-900 dark:text-white" />
            </div>
            <div class="mb-6">
              <label for="p-admin" class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Mot de passe</label>
              <input id="p-admin" v-model="password" type="password" required class="h-11 w-full rounded-lg border border-gray-300 px-3 dark:border-gray-700 dark:bg-gray-900 dark:text-white" />
            </div>
            <button
              type="submit"
              :disabled="auth.isLoading"
              class="w-full py-2.5 px-4 bg-blue-600 text-white font-medium rounded-md hover:bg-blue-700 disabled:opacity-50"
            >
              {{ auth.isLoading ? 'Connexion...' : 'Se connecter' }}
            </button>
          </form>
        </div>
      </div>
    </div>
  </div>
</template>
