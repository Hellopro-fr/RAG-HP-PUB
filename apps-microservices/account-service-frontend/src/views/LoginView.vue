<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { User, Lock, Loader2 } from 'lucide-vue-next'
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

const brandTitle = computed(() =>
  oauthMode.value ? `Connexion à ${branding.value?.name ?? 'votre service'}` : 'Account Service',
)
const subtitle = computed(() =>
  oauthMode.value ? 'Authentifiez-vous pour accéder à ce service.' : 'Accédez au tableau de bord.',
)
const logoUrl = computed(() => branding.value?.logo_url || '/images/servers/hp-logo.svg')

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
    <!-- Left panel: branding (hidden on mobile) -->
    <div class="hidden lg:flex lg:w-1/2 bg-[#1C2434] relative flex-col items-center justify-center px-12">
      <!-- Decorative shapes -->
      <div class="absolute top-0 left-0 w-full h-full overflow-hidden pointer-events-none">
        <div class="absolute -top-20 -left-20 w-64 h-64 rounded-full bg-blue-500/10" />
        <div class="absolute bottom-10 right-10 w-48 h-48 rounded-full bg-indigo-500/10" />
        <div class="absolute top-1/3 right-1/4 w-32 h-32 rounded-full bg-cyan-500/10" />
      </div>

      <div class="relative z-10 text-center max-w-md">
        <!-- Logo / Icon -->
        <div class="mx-auto mb-8 w-20 h-20 rounded-2xl bg-white flex items-center justify-center p-3 shadow-lg">
          <img :src="logoUrl" :alt="branding?.name ?? 'Account Service'" class="w-full h-full object-contain" />
        </div>

        <h1 class="text-3xl font-bold text-white mb-4">{{ brandTitle }}</h1>
        <p class="text-gray-400 text-base leading-relaxed">
          Plateforme d'identité unifiée Hellopro.
        </p>
      </div>
    </div>

    <!-- Right panel: login form -->
    <div class="w-full lg:w-1/2 flex items-center justify-center bg-gray-100 dark:bg-gray-950 px-6">
      <div class="w-full max-w-sm">
        <!-- Mobile-only branding -->
        <div class="lg:hidden text-center mb-8">
          <div class="mx-auto mb-4 w-14 h-14 rounded-xl bg-white flex items-center justify-center p-2 shadow-theme-sm border border-gray-200 dark:border-gray-700">
            <img :src="logoUrl" :alt="branding?.name ?? 'Account Service'" class="w-full h-full object-contain" />
          </div>
          <h1 class="text-2xl font-bold text-gray-900 dark:text-white">{{ brandTitle }}</h1>
        </div>

        <div class="bg-white dark:bg-gray-900 rounded-lg shadow-theme-md p-8">
          <h2 class="text-xl font-semibold text-gray-900 dark:text-white mb-1">Connexion</h2>
          <p class="text-sm text-gray-500 dark:text-gray-400 mb-6">{{ subtitle }}</p>

          <div
            v-if="errorMessage"
            class="mb-4 p-3 bg-error-50 dark:bg-error-500/15 border border-error-200 dark:border-error-500/30 rounded-md text-sm text-error-600 dark:text-error-400"
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
              <label for="u-oauth" class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Nom d'utilisateur
              </label>
              <div class="relative">
                <span class="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 dark:text-gray-500">
                  <User class="w-4 h-4" />
                </span>
                <input
                  id="u-oauth"
                  name="username"
                  v-model="username"
                  type="text"
                  required
                  placeholder="Entrez votre nom d'utilisateur"
                  class="h-11 w-full rounded-lg border border-gray-300 bg-transparent pl-10 pr-4 py-2.5 text-sm text-gray-800 shadow-theme-xs placeholder:text-gray-400 focus:border-brand-300 focus:outline-hidden focus:ring-3 focus:ring-brand-500/10 dark:border-gray-700 dark:bg-gray-900 dark:text-white/90 dark:placeholder:text-white/30"
                />
              </div>
            </div>

            <div class="mb-6">
              <label for="p-oauth" class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Mot de passe
              </label>
              <div class="relative">
                <span class="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 dark:text-gray-500">
                  <Lock class="w-4 h-4" />
                </span>
                <input
                  id="p-oauth"
                  name="password"
                  v-model="password"
                  type="password"
                  required
                  placeholder="Entrez votre mot de passe"
                  class="h-11 w-full rounded-lg border border-gray-300 bg-transparent pl-10 pr-4 py-2.5 text-sm text-gray-800 shadow-theme-xs placeholder:text-gray-400 focus:border-brand-300 focus:outline-hidden focus:ring-3 focus:ring-brand-500/10 dark:border-gray-700 dark:bg-gray-900 dark:text-white/90 dark:placeholder:text-white/30"
                />
              </div>
            </div>

            <button
              type="submit"
              class="w-full py-2.5 px-4 bg-brand-500 text-white font-medium rounded-md hover:bg-brand-600 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
            >
              Se connecter
            </button>
          </form>

          <!-- Admin UI mode: JS-driven JSON POST /api/v1/login -->
          <form v-else @submit.prevent="handleAdminLogin">
            <div class="mb-4">
              <label for="u-admin" class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Nom d'utilisateur
              </label>
              <div class="relative">
                <span class="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 dark:text-gray-500">
                  <User class="w-4 h-4" />
                </span>
                <input
                  id="u-admin"
                  v-model="username"
                  type="text"
                  required
                  placeholder="Entrez votre nom d'utilisateur"
                  class="h-11 w-full rounded-lg border border-gray-300 bg-transparent pl-10 pr-4 py-2.5 text-sm text-gray-800 shadow-theme-xs placeholder:text-gray-400 focus:border-brand-300 focus:outline-hidden focus:ring-3 focus:ring-brand-500/10 dark:border-gray-700 dark:bg-gray-900 dark:text-white/90 dark:placeholder:text-white/30"
                />
              </div>
            </div>

            <div class="mb-6">
              <label for="p-admin" class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Mot de passe
              </label>
              <div class="relative">
                <span class="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 dark:text-gray-500">
                  <Lock class="w-4 h-4" />
                </span>
                <input
                  id="p-admin"
                  v-model="password"
                  type="password"
                  required
                  placeholder="Entrez votre mot de passe"
                  class="h-11 w-full rounded-lg border border-gray-300 bg-transparent pl-10 pr-4 py-2.5 text-sm text-gray-800 shadow-theme-xs placeholder:text-gray-400 focus:border-brand-300 focus:outline-hidden focus:ring-3 focus:ring-brand-500/10 dark:border-gray-700 dark:bg-gray-900 dark:text-white/90 dark:placeholder:text-white/30"
                />
              </div>
            </div>

            <button
              type="submit"
              :disabled="auth.isLoading"
              class="w-full py-2.5 px-4 bg-brand-500 text-white font-medium rounded-md hover:bg-brand-600 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
            >
              <Loader2 v-if="auth.isLoading" class="w-4 h-4 animate-spin" />
              Se connecter
            </button>
          </form>
        </div>
      </div>
    </div>
  </div>
</template>
