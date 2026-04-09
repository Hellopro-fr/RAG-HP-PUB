<template>
  <!-- Mobile backdrop -->
  <div
    v-if="modelValue"
    class="fixed inset-0 z-40 bg-black/60 lg:hidden"
    @click="$emit('update:modelValue', false)"
  />

  <!-- Sidebar -->
  <aside
    :class="[
      'fixed left-0 top-0 z-50 flex h-screen w-64 flex-col bg-[#1C2434] text-white',
      'transition-transform duration-300 ease-in-out',
      'lg:translate-x-0',
      modelValue ? 'translate-x-0' : '-translate-x-full'
    ]"
  >
    <!-- Logo -->
    <div class="flex items-center gap-2 border-b border-white/10 px-6 py-5">
      <i class="pi pi-box text-xl text-blue-400" />
      <span class="text-lg font-bold tracking-wide">MCP Gateway</span>
    </div>

    <!-- Navigation -->
    <nav class="sidebar-scrollbar mt-4 flex-1 overflow-y-auto px-4">
      <ul class="flex flex-col gap-1">
        <li v-for="item in navItems" :key="item.to">
          <RouterLink
            :to="item.to"
            class="flex items-center gap-3 rounded-md px-4 py-2.5 text-sm font-medium transition-colors"
            :class="[
              isActive(item.to)
                ? 'bg-white/10 text-white'
                : 'text-gray-400 hover:bg-white/5 hover:text-white'
            ]"
            @click="$emit('update:modelValue', false)"
          >
            <i :class="[item.icon, 'text-base']" />
            {{ item.label }}
          </RouterLink>
        </li>
      </ul>
    </nav>
  </aside>
</template>

<script setup lang="ts">
import { RouterLink, useRoute } from 'vue-router'

defineProps<{
  modelValue: boolean
}>()

defineEmits<{
  'update:modelValue': [value: boolean]
}>()

const route = useRoute()

const navItems = [
  { to: '/servers', label: 'Serveurs', icon: 'pi pi-server' },
  { to: '/tokens', label: 'Config MCP', icon: 'pi pi-key' },
  { to: '/oauth2', label: 'OAuth2', icon: 'pi pi-shield' }
]

function isActive(path: string): boolean {
  return route.path.startsWith(path)
}
</script>
