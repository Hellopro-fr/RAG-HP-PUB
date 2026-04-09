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
        <div class="mx-auto mb-8 w-20 h-20 rounded-2xl bg-blue-600 flex items-center justify-center">
          <i class="pi pi-server text-3xl text-white" />
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
    <div class="w-full lg:w-1/2 flex items-center justify-center bg-gray-100 px-6">
      <div class="w-full max-w-sm">
        <!-- Mobile-only branding -->
        <div class="lg:hidden text-center mb-8">
          <div class="mx-auto mb-4 w-14 h-14 rounded-xl bg-blue-600 flex items-center justify-center">
            <i class="pi pi-server text-2xl text-white" />
          </div>
          <h1 class="text-2xl font-bold text-gray-900">MCP Gateway</h1>
        </div>

        <div class="bg-white rounded-lg shadow-md p-8">
          <h2 class="text-xl font-semibold text-gray-900 mb-1">Connexion</h2>
          <p class="text-sm text-gray-500 mb-6">Connectez-vous pour accéder au tableau de bord</p>

          <div
            v-if="errorMessage"
            class="mb-4 p-3 bg-red-50 border border-red-200 rounded-md text-sm text-red-700"
          >
            {{ errorMessage }}
          </div>

          <form @submit.prevent="handleLogin">
            <div class="mb-4">
              <label for="username" class="block text-sm font-medium text-gray-700 mb-1">
                Nom d'utilisateur
              </label>
              <div class="relative">
                <span class="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400">
                  <i class="pi pi-user text-sm" />
                </span>
                <input
                  id="username"
                  v-model="username"
                  type="text"
                  required
                  placeholder="Entrez votre nom d'utilisateur"
                  class="w-full pl-10 pr-3 py-2.5 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                />
              </div>
            </div>

            <div class="mb-6">
              <label for="password" class="block text-sm font-medium text-gray-700 mb-1">
                Mot de passe
              </label>
              <div class="relative">
                <span class="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400">
                  <i class="pi pi-lock text-sm" />
                </span>
                <input
                  id="password"
                  v-model="password"
                  type="password"
                  required
                  placeholder="Entrez votre mot de passe"
                  class="w-full pl-10 pr-3 py-2.5 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                />
              </div>
            </div>

            <button
              type="submit"
              :disabled="authStore.isLoading"
              class="w-full py-2.5 px-4 bg-blue-600 text-white font-medium rounded-md hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
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
import { ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()

const username = ref('')
const password = ref('')
const errorMessage = ref('')

async function handleLogin() {
  errorMessage.value = ''
  try {
    await authStore.login(username.value, password.value)
    const redirect = (route.query.redirect as string) || '/servers'
    router.push(redirect)
  } catch (e) {
    errorMessage.value = e instanceof Error ? e.message : 'Erreur de connexion'
  }
}
</script>
