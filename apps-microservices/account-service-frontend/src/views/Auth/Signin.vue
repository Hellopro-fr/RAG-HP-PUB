<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import AuthCard from '../../components/auth/AuthCard.vue'
import { useOAuthFlow } from '../../composables/useOAuthFlow'

const router = useRouter()
const { params, submitLogin } = useOAuthFlow()

const email = ref('')
const password = ref('')
const submitting = ref(false)
const errorMessage = ref('')

async function onSubmit() {
  errorMessage.value = ''
  if (!params.value) {
    errorMessage.value = 'Missing OAuth parameters.'
    return
  }
  submitting.value = true
  try {
    const res = await submitLogin(email.value, password.value)
    if (res.redirect) {
      window.location.assign(res.redirect)
      return
    }
    if (res.next === '/consent') {
      await router.push({ path: '/consent', query: router.currentRoute.value.query })
      return
    }
    errorMessage.value = 'Unexpected response from server.'
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : 'login_failed'
    errorMessage.value =
      msg === 'access_denied' ? 'Invalid email or password.' :
      msg === 'upstream_unavailable' ? 'Service temporarily unavailable. Try again.' :
      'Sign-in failed.'
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <AuthCard title="Sign in" subtitle="Enter your HelloPro credentials">
    <form class="space-y-4" @submit.prevent="onSubmit" data-test="signin-form">
      <div>
        <label class="block text-sm font-medium text-gray-700 dark:text-gray-200">Email</label>
        <input
          v-model="email" type="email" required autocomplete="email"
          class="mt-1 block w-full rounded-md border-gray-300 shadow-sm
                 focus:border-indigo-500 focus:ring-indigo-500 dark:bg-gray-700 dark:text-white"
          data-test="email"
        />
      </div>
      <div>
        <label class="block text-sm font-medium text-gray-700 dark:text-gray-200">Password</label>
        <input
          v-model="password" type="password" required autocomplete="current-password"
          class="mt-1 block w-full rounded-md border-gray-300 shadow-sm
                 focus:border-indigo-500 focus:ring-indigo-500 dark:bg-gray-700 dark:text-white"
          data-test="password"
        />
      </div>
      <p v-if="errorMessage" class="text-sm text-red-600" data-test="error">{{ errorMessage }}</p>
      <button
        type="submit" :disabled="submitting"
        class="w-full rounded-md bg-indigo-600 px-4 py-2 text-white hover:bg-indigo-700
               disabled:opacity-50"
        data-test="submit"
      >
        {{ submitting ? 'Signing in...' : 'Sign in' }}
      </button>
    </form>
  </AuthCard>
</template>
