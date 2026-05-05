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
          <img src="/images/servers/hp-logo.svg" alt="Hellopro" class="w-full h-full object-contain" />
        </div>

        <h1 class="text-3xl font-bold text-white mb-4">MCP Gateway</h1>
        <p class="text-gray-400 text-base leading-relaxed">
          Plateforme de gestion centralisée pour vos serveurs MCP.
          Configurez vos serveurs, gérez les jetons d'accès et les clients OAuth2
          depuis une interface unifiée.
        </p>
      </div>
    </div>

    <!-- Right panel: login form -->
    <div class="w-full lg:w-1/2 flex items-center justify-center bg-gray-100 dark:bg-gray-950 px-6">
      <div class="w-full max-w-sm">
        <!-- Mobile-only branding -->
        <div class="lg:hidden text-center mb-8">
          <div class="mx-auto mb-4 w-14 h-14 rounded-xl bg-white flex items-center justify-center p-2 shadow-theme-sm border border-gray-200 dark:border-gray-700">
            <img src="/images/servers/hp-logo.svg" alt="Hellopro" class="w-full h-full object-contain" />
          </div>
          <h1 class="text-2xl font-bold text-gray-900 dark:text-white">MCP Gateway</h1>
        </div>

        <div class="bg-white dark:bg-gray-900 rounded-lg shadow-theme-md p-8">
          <h2 class="text-xl font-semibold text-gray-900 dark:text-white mb-1">Connexion</h2>
          <p class="text-sm text-gray-500 dark:text-gray-400 mb-6">Connectez-vous pour accéder au tableau de bord</p>

          <div
            v-if="errorMessage"
            class="mb-4 p-3 bg-error-50 dark:bg-error-500/15 border border-error-200 dark:border-error-500/30 rounded-md text-sm text-error-600 dark:text-error-400"
          >
            {{ errorMessage }}
          </div>

          <form @submit.prevent="handleLogin">
            <div class="mb-4">
              <label for="username" class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Nom d'utilisateur
              </label>
              <div class="relative">
                <span class="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 dark:text-gray-500">
                  <i class="pi pi-user text-sm" />
                </span>
                <input
                  id="username"
                  v-model="username"
                  type="text"
                  required
                  placeholder="Entrez votre nom d'utilisateur"
                  class="h-11 w-full rounded-lg border border-gray-300 bg-transparent pl-10 pr-4 py-2.5 text-sm text-gray-800 shadow-theme-xs placeholder:text-gray-400 focus:border-brand-300 focus:outline-hidden focus:ring-3 focus:ring-brand-500/10 dark:border-gray-700 dark:bg-gray-900 dark:text-white/90 dark:placeholder:text-white/30"
                />
              </div>
            </div>

            <div class="mb-6">
              <label for="password" class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Mot de passe
              </label>
              <div class="relative">
                <span class="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 dark:text-gray-500">
                  <i class="pi pi-lock text-sm" />
                </span>
                <input
                  id="password"
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
              :disabled="authStore.isLoading"
              class="w-full py-2.5 px-4 bg-brand-500 text-white font-medium rounded-md hover:bg-brand-600 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
            >
              <i v-if="authStore.isLoading" class="pi pi-spinner pi-spin" />
              Se connecter
            </button>
          </form>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()

const username = ref('')
const password = ref('')
const errorMessage = ref('')

// In SSO mode this view should never render the form — the router redirects
// out before mount in 99% of cases, but a deep-link to /login still lands
// here. Fire the redirect ourselves and short-circuit.
onMounted(() => {
  if (authStore.ssoMode) {
    const target = (route.query.redirect as string) || '/'
    authStore.redirectToLogin(target)
  }
})

async function handleLogin() {
  errorMessage.value = ''
  try {
    await authStore.login(username.value, password.value)
    const redirect = (route.query.redirect as string) || '/'
    router.push(redirect)
  } catch (e) {
    errorMessage.value = e instanceof Error ? e.message : 'Erreur de connexion'
  }
}
</script>
