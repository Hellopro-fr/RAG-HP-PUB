<template>
  <div class="relative" ref="dropdownRef">
    <button
      class="flex items-center text-gray-700 dark:text-gray-400"
      @click.prevent="toggleDropdown"
    >
      <span class="mr-3 overflow-hidden rounded-full h-9 w-9 bg-blue-500 flex items-center justify-center text-white text-sm font-semibold">
        {{ initials }}
      </span>

      <span class="block mr-1 font-medium text-theme-sm">{{ display }}</span>

      <ChevronDownIcon :class="{ 'rotate-180': dropdownOpen }" />
    </button>

    <div
      v-if="dropdownOpen"
      class="absolute right-0 mt-[17px] flex w-[260px] flex-col rounded-2xl border border-gray-200 bg-white p-3 shadow-theme-lg dark:border-gray-800 dark:bg-gray-dark"
    >
      <div>
        <span class="block font-medium text-gray-700 text-theme-sm dark:text-gray-400">
          {{ auth.user?.display_name || auth.user?.email }}
        </span>
        <span class="mt-0.5 block text-theme-xs text-gray-500 dark:text-gray-400">
          {{ auth.user?.email }} <span v-if="auth.isAdmin" class="ml-1 px-1.5 py-0.5 text-[10px] bg-blue-100 text-blue-700 rounded">admin</span>
        </span>
      </div>

      <ul class="flex flex-col gap-1 pt-4 pb-3 border-b border-gray-200 dark:border-gray-800">
        <li>
          <router-link to="/me" @click="closeDropdown"
            class="flex items-center gap-3 px-3 py-2 font-medium text-gray-700 rounded-lg group text-theme-sm hover:bg-gray-100 hover:text-gray-700 dark:text-gray-400 dark:hover:bg-white/5 dark:hover:text-gray-300">
            <UserCircleIcon class="text-gray-500 group-hover:text-gray-700 dark:group-hover:text-gray-300" />
            Mon profil
          </router-link>
        </li>
        <li v-if="auth.isAdmin">
          <router-link to="/admin/parameters" @click="closeDropdown"
            class="flex items-center gap-3 px-3 py-2 font-medium text-gray-700 rounded-lg group text-theme-sm hover:bg-gray-100 hover:text-gray-700 dark:text-gray-400 dark:hover:bg-white/5 dark:hover:text-gray-300">
            <SettingsIcon class="text-gray-500 group-hover:text-gray-700 dark:group-hover:text-gray-300" />
            Paramètres
          </router-link>
        </li>
      </ul>
      <button
        type="button"
        @click="signOut"
        class="flex items-center gap-3 px-3 py-2 mt-3 font-medium text-gray-700 rounded-lg group text-theme-sm hover:bg-gray-100 hover:text-gray-700 dark:text-gray-400 dark:hover:bg-white/5 dark:hover:text-gray-300"
      >
        <LogoutIcon class="text-gray-500 group-hover:text-gray-700 dark:group-hover:text-gray-300" />
        Se déconnecter
      </button>
    </div>
  </div>
</template>

<script setup>
import { UserCircleIcon, ChevronDownIcon, LogoutIcon, SettingsIcon } from '@/icons'
import { computed, ref, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const router = useRouter()
const dropdownOpen = ref(false)
const dropdownRef = ref(null)

const display = computed(() => auth.user?.display_name || auth.user?.email || '')
const initials = computed(() => {
  const src = (auth.user?.display_name || auth.user?.email || '?').trim()
  return src.slice(0, 2).toUpperCase()
})

const toggleDropdown = () => { dropdownOpen.value = !dropdownOpen.value }
const closeDropdown = () => { dropdownOpen.value = false }

const signOut = async () => {
  closeDropdown()
  await auth.logout()
  router.push('/login')
}

const handleClickOutside = (event) => {
  if (dropdownRef.value && !dropdownRef.value.contains(event.target)) {
    closeDropdown()
  }
}

onMounted(() => document.addEventListener('click', handleClickOutside))
onUnmounted(() => document.removeEventListener('click', handleClickOutside))
</script>
