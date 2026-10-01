<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { LogOut, KeyRound, Pencil } from 'lucide-vue-next'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const router = useRouter()

// Initials are derived from display_name when present, falling back to the
// local part of the email so the avatar circle is never blank.
const initials = computed(() => {
  const source = auth.user?.display_name || auth.user?.email || ''
  const parts = source.split(/[\s._-]+/).filter(Boolean)
  if (parts.length === 0) return '?'
  if (parts.length === 1) return parts[0]!.slice(0, 2).toUpperCase()
  return (parts[0]![0]! + parts[1]![0]!).toUpperCase()
})

const roleLabel = computed(() => (auth.user?.is_admin ? 'Administrateur' : 'Utilisateur'))

async function handleLogout() {
  await auth.logout()
  router.push('/login')
}

function goToSessions() {
  router.push('/me/sessions')
}
</script>

<template>
  <div class="px-4 py-6 sm:px-6 lg:px-8 max-w-5xl mx-auto space-y-6">
    <h1 class="text-2xl font-semibold text-gray-900 dark:text-white">Profil</h1>

    <!-- Identity card: avatar + name + role + email -->
    <section class="rounded-2xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-5 lg:p-6 shadow-theme-xs">
      <div class="flex flex-col gap-5 lg:flex-row lg:items-center lg:justify-between">
        <div class="flex items-center gap-4">
          <div class="w-20 h-20 rounded-full bg-brand-500/10 flex items-center justify-center text-brand-600 dark:text-brand-400 text-2xl font-semibold border border-brand-100 dark:border-brand-500/20">
            {{ initials }}
          </div>
          <div>
            <h2 class="text-xl font-semibold text-gray-900 dark:text-white">
              {{ auth.user?.display_name || auth.user?.email || '—' }}
            </h2>
            <p class="mt-1 text-sm text-gray-500 dark:text-gray-400">{{ roleLabel }}</p>
            <p class="mt-1 text-sm text-gray-500 dark:text-gray-400">{{ auth.user?.email }}</p>
          </div>
        </div>
        <div class="flex gap-2">
          <button
            type="button"
            class="inline-flex items-center gap-2 px-4 py-2 rounded-lg border border-gray-200 dark:border-gray-700 text-sm font-medium text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-white/[0.03]"
            @click="goToSessions"
          >
            <KeyRound class="w-4 h-4" />
            Sessions actives
          </button>
          <button
            type="button"
            class="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-error-500 text-white text-sm font-medium hover:bg-error-600"
            @click="handleLogout"
          >
            <LogOut class="w-4 h-4" />
            Se déconnecter
          </button>
        </div>
      </div>
    </section>

    <!-- Personal information card. Editing the display_name and email lives
         on the backend roadmap; the form is intentionally read-only for now
         and the Edit button surfaces the limitation. -->
    <section class="rounded-2xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-5 lg:p-6 shadow-theme-xs">
      <header class="flex items-center justify-between mb-5">
        <h3 class="text-base font-semibold text-gray-900 dark:text-white">Informations personnelles</h3>
        <button
          type="button"
          disabled
          class="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg border border-gray-200 dark:border-gray-700 text-sm text-gray-400 dark:text-gray-500 cursor-not-allowed"
          title="Modification non disponible"
        >
          <Pencil class="w-3.5 h-3.5" />
          Modifier
        </button>
      </header>
      <dl class="grid grid-cols-1 sm:grid-cols-2 gap-x-8 gap-y-4">
        <div>
          <dt class="text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">Nom d'affichage</dt>
          <dd class="mt-1 text-sm text-gray-900 dark:text-white">
            {{ auth.user?.display_name || '—' }}
          </dd>
        </div>
        <div>
          <dt class="text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">E-mail</dt>
          <dd class="mt-1 text-sm text-gray-900 dark:text-white">{{ auth.user?.email || '—' }}</dd>
        </div>
        <div>
          <dt class="text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">Rôle</dt>
          <dd class="mt-1 text-sm">
            <span
              class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium"
              :class="auth.user?.is_admin
                ? 'bg-brand-100 text-brand-700 dark:bg-brand-500/15 dark:text-brand-300'
                : 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300'"
            >
              {{ roleLabel }}
            </span>
          </dd>
        </div>
        <div>
          <dt class="text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">Statut</dt>
          <dd class="mt-1 text-sm text-gray-900 dark:text-white">
            <span
              class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium"
              :class="auth.user?.is_allowed
                ? 'bg-success-50 text-success-700 dark:bg-success-500/15 dark:text-success-400'
                : 'bg-error-50 text-error-700 dark:bg-error-500/15 dark:text-error-400'"
            >
              {{ auth.user?.is_allowed ? 'Autorisé' : 'Non autorisé' }}
            </span>
          </dd>
        </div>
      </dl>
    </section>

    <!-- Sessions card: redirects to the existing UserSessionsView. -->
    <section class="rounded-2xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-5 lg:p-6 shadow-theme-xs">
      <header class="flex items-center justify-between mb-3">
        <h3 class="text-base font-semibold text-gray-900 dark:text-white">Sécurité</h3>
      </header>
      <p class="text-sm text-gray-500 dark:text-gray-400 mb-4">
        Affichez et révoquez les sessions actives liées à votre compte.
      </p>
      <button
        type="button"
        class="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-brand-500 text-white text-sm font-medium hover:bg-brand-600"
        @click="goToSessions"
      >
        <KeyRound class="w-4 h-4" />
        Gérer les sessions
      </button>
    </section>
  </div>
</template>
