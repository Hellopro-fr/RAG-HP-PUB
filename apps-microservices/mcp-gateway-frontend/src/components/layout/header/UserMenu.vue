<template>
  <div class="relative" ref="dropdownRef">
    <button
      class="flex items-center text-gray-700 dark:text-gray-400"
      @click.prevent="toggleDropdown"
    >
      <span
        class="mr-3 flex items-center justify-center overflow-hidden rounded-full h-11 w-11 bg-brand-100 text-brand-600 dark:bg-brand-500/20 dark:text-brand-400 font-semibold text-sm"
      >
        {{ userInitials }}
      </span>
      <span class="block mr-1 font-medium text-theme-sm">{{ displayName }}</span>
      <i
        :class="['pi pi-chevron-down text-xs transition-transform duration-200', { 'rotate-180': dropdownOpen }]"
      />
    </button>

    <!-- Dropdown -->
    <div
      v-if="dropdownOpen"
      class="absolute right-0 mt-[17px] flex w-[260px] flex-col rounded-2xl border border-gray-200 bg-white p-3 shadow-theme-lg dark:border-gray-800 dark:bg-gray-900 z-20"
    >
      <div>
        <span class="block font-medium text-gray-700 text-theme-sm dark:text-gray-400">
          {{ authStore.user?.email || 'Administrateur' }}
        </span>
      </div>

      <div class="pt-3 mt-3 border-t border-gray-200 dark:border-gray-800">
        <button
          @click="handleLogout"
          class="flex items-center gap-3 w-full px-3 py-2 font-medium text-gray-700 rounded-lg group text-theme-sm hover:bg-gray-100 hover:text-gray-700 dark:text-gray-400 dark:hover:bg-white/5 dark:hover:text-gray-300"
        >
          <i class="pi pi-sign-out text-gray-500 group-hover:text-gray-700 dark:group-hover:text-gray-300" />
          Deconnexion
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue';
import { useRouter } from 'vue-router';
import { useAuthStore } from '@/stores/auth';

const router = useRouter();
const authStore = useAuthStore();

const dropdownOpen = ref(false);
const dropdownRef = ref<HTMLElement | null>(null);

const displayName = computed(() => {
  const email = authStore.user?.email;
  if (!email) return 'Admin';
  return email.split('@')[0];
});

const userInitials = computed(() => {
  const email = authStore.user?.email;
  if (!email) return 'A';
  const name = email.split('@')[0] ?? '';
  return name.substring(0, 2).toUpperCase();
});

const toggleDropdown = (): void => {
  dropdownOpen.value = !dropdownOpen.value;
};

const closeDropdown = (): void => {
  dropdownOpen.value = false;
};

async function handleLogout(): Promise<void> {
  await authStore.logout();
  router.push('/login');
  closeDropdown();
}

const handleClickOutside = (event: MouseEvent): void => {
  if (dropdownRef.value && !dropdownRef.value.contains(event.target as Node)) {
    closeDropdown();
  }
};

onMounted(() => {
  document.addEventListener('click', handleClickOutside);
});

onUnmounted(() => {
  document.removeEventListener('click', handleClickOutside);
});
</script>
