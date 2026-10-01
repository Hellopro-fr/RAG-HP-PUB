<template>
  <div>
    <!-- Breadcrumb -->
    <nav class="mb-6 text-sm">
      <router-link to="/docs" class="text-brand-500 hover:text-brand-600 dark:text-brand-400">
        Documentation
      </router-link>
      <span class="mx-2 text-gray-400">/</span>
      <router-link to="/install-guide" class="text-brand-500 hover:text-brand-600 dark:text-brand-400">
        Guide d'installation
      </router-link>
      <span class="mx-2 text-gray-400">/</span>
      <span class="text-gray-600 dark:text-gray-300">{{ cmd?.label || '...' }}</span>
    </nav>

    <CrossSectionLink
      to="/docs"
      icon="pi-book"
      message="Decouvrez les outils MCP et leur configuration."
      link-label="Voir la documentation"
    />

    <!-- Loading skeleton -->
    <div v-if="loading" class="animate-pulse" aria-hidden="true">
      <div class="mb-8">
        <div class="flex items-center gap-4">
          <div class="w-12 h-12 rounded-lg bg-gray-200 dark:bg-gray-800" />
          <div class="flex-1">
            <div class="h-7 w-1/3 rounded bg-gray-200 dark:bg-gray-800 mb-2" />
            <div class="h-3 w-2/3 rounded bg-gray-100 dark:bg-gray-800" />
          </div>
        </div>
        <div class="mt-4 space-y-2">
          <div class="h-3 w-5/6 rounded bg-gray-100 dark:bg-gray-800" />
          <div class="h-3 w-2/3 rounded bg-gray-100 dark:bg-gray-800" />
        </div>
      </div>
      <div v-for="i in 2" :key="i" class="mb-8">
        <div class="h-5 w-40 rounded bg-gray-200 dark:bg-gray-800 mb-4" />
        <div class="h-24 w-full rounded-lg bg-gray-100 dark:bg-gray-800" />
      </div>
    </div>

    <!-- Not found -->
    <div v-else-if="!cmd" class="text-center py-16">
      <div class="w-16 h-16 mx-auto mb-4 rounded-full bg-red-50 dark:bg-red-900/20 flex items-center justify-center">
        <svg class="w-8 h-8 text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
          <path stroke-linecap="round" stroke-linejoin="round" d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z" />
        </svg>
      </div>
      <p class="text-gray-600 dark:text-gray-400 mb-4">Guide introuvable.</p>
      <router-link
        to="/install-guide"
        class="inline-block px-4 py-2 text-sm font-medium text-brand-500 border border-brand-300 rounded-md hover:bg-brand-50 dark:hover:bg-brand-500/10"
      >
        Retour a la liste
      </router-link>
    </div>

    <!-- Guide content -->
    <div v-else>
      <!-- Header -->
      <div class="mb-8">
        <div class="flex items-center gap-4">
          <div
            class="w-12 h-12 rounded-lg flex items-center justify-center"
            :class="cmd.color"
          >
            <i class="pi text-xl" :class="cmd.icon" />
          </div>
          <div>
            <h1 class="text-2xl font-bold text-gray-900 dark:text-white">{{ cmd.label }}</h1>
            <p class="text-sm text-gray-500 dark:text-gray-400">{{ cmd.description }}</p>
          </div>
        </div>
        <div class="mt-4 text-sm text-gray-600 dark:text-gray-400" v-safe-html="cmd.intro" />
      </div>

      <!-- Dynamic content elements -->
      <template v-for="(el, elIdx) in (cmd.content || [])" :key="elIdx">
        <!-- OS Install -->
        <section v-if="el.type === 'os-install'" class="mb-8">
          <h2 class="text-lg font-semibold text-gray-900 dark:text-white mb-4">
            Installation
          </h2>
          <PageHeaderTabs
            v-model="activeOS"
            :tabs="osTabs"
          >
            <div class="space-y-4">
              <div
                v-for="(option, i) in installWithTerminal(activeOS)"
                :key="i"
                class="flex gap-3"
              >
                <span
                  v-if="option.noNumber"
                  class="flex-shrink-0 w-7 h-7 rounded-full bg-gray-200 dark:bg-gray-700 text-gray-600 dark:text-gray-300 text-sm flex items-center justify-center"
                >
                  <i class="pi pi-desktop text-xs" />
                </span>
                <span
                  v-else
                  class="flex-shrink-0 w-7 h-7 rounded-full bg-brand-500 text-white text-sm font-semibold flex items-center justify-center"
                >
                  {{ stepNumber(installWithTerminal(activeOS)!, i) }}
                </span>
                <div class="pt-0.5 flex-1">
                  <p class="font-medium text-gray-900 dark:text-white text-sm">{{ option.label }}</p>
                  <p v-if="option.note" class="text-sm text-gray-600 dark:text-gray-400 mt-0.5" v-safe-html="option.note" />
                  <div v-if="option.code" class="mt-2">
                    <CodeBlock :code="option.code" @copy="handleCopy" />
                  </div>
                </div>
              </div>
            </div>
          </PageHeaderTabs>
        </section>

        <!-- Verify -->
        <section v-else-if="el.type === 'verify'" class="mb-8">
          <h2 class="text-lg font-semibold text-gray-900 dark:text-white mb-4">
            {{ el.props.title || 'Verification' }}
          </h2>
          <CodeBlock :code="el.props.code || cmd.verify" @copy="handleCopy" />
        </section>

        <!-- MCP Config — content sourced from executor.mcp_config (top-level field) -->
        <section v-else-if="el.type === 'mcp-config'" class="mb-8">
          <h2 class="text-lg font-semibold text-gray-900 dark:text-white mb-4">
            {{ el.props.title || 'Configuration MCP' }}
          </h2>
          <CodeBlock :code="cmd.mcp_config || el.props.code || ''" @copy="handleCopy" />
        </section>

        <!-- CLI Command -->
        <section v-else-if="el.type === 'cli-command'" class="mb-8">
          <h2 class="text-lg font-semibold text-gray-900 dark:text-white mb-4">
            {{ el.props.title || 'Commande Claude Code' }}
          </h2>
          <CodeBlock :code="el.props.code || cmd.cli_add_cmd" @copy="handleCopy" />
        </section>

        <!-- Note -->
        <div
          v-else-if="el.type === 'note'"
          class="mb-8 rounded-lg p-3 text-sm"
          :class="el.props.cssClass || 'bg-amber-50 dark:bg-amber-500/10 border border-amber-200 dark:border-amber-500/30 text-amber-800 dark:text-amber-300'"
        >
          <strong>{{ el.props.label }}</strong> <span v-safe-html="el.props.text" />
        </div>

        <!-- Text -->
        <div
          v-else-if="el.type === 'text'"
          class="mb-8 text-sm text-gray-700 dark:text-gray-300"
          v-safe-html="el.props.content"
        />

        <!-- Divider -->
        <hr v-else-if="el.type === 'divider'" class="border-gray-200 dark:border-gray-700 mb-8" />
      </template>

      <!-- Fallback: old-style fields if no content elements -->
      <template v-if="!cmd.content || cmd.content.length === 0">
        <section v-if="cmd.install" class="mb-8">
          <h2 class="text-lg font-semibold text-gray-900 dark:text-white mb-4">Installation</h2>
          <PageHeaderTabs v-model="activeOS" :tabs="osTabs">
            <div class="space-y-4">
              <div v-for="(option, i) in installWithTerminal(activeOS)" :key="i" class="flex gap-3">
                <span v-if="option.noNumber" class="flex-shrink-0 w-7 h-7 rounded-full bg-gray-200 dark:bg-gray-700 text-gray-600 dark:text-gray-300 text-sm flex items-center justify-center">
                  <i class="pi pi-desktop text-xs" />
                </span>
                <span v-else class="flex-shrink-0 w-7 h-7 rounded-full bg-brand-500 text-white text-sm font-semibold flex items-center justify-center">
                  {{ stepNumber(installWithTerminal(activeOS)!, i) }}
                </span>
                <div class="pt-0.5 flex-1">
                  <p class="font-medium text-gray-900 dark:text-white text-sm">{{ option.label }}</p>
                  <p v-if="option.note" class="text-sm text-gray-600 dark:text-gray-400 mt-0.5" v-safe-html="option.note" />
                  <div v-if="option.code" class="mt-2"><CodeBlock :code="option.code" @copy="handleCopy" /></div>
                </div>
              </div>
            </div>
          </PageHeaderTabs>
        </section>
        <section v-if="cmd.verify" class="mb-8">
          <h2 class="text-lg font-semibold text-gray-900 dark:text-white mb-4">Verification</h2>
          <CodeBlock :code="cmd.verify" @copy="handleCopy" />
        </section>
      </template>


    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import CodeBlock from '@/components/shared/CodeBlock.vue'
import CrossSectionLink from '@/components/shared/CrossSectionLink.vue'
import PageHeaderTabs from '@/components/common/PageHeaderTabs.vue'
import { useClipboard } from '@/composables/useClipboard'
import { installGuidesPublicApi } from '@/api/install-guides'
import type { InstallExecutor, InstallOption } from '@/types/install-guide'

const route = useRoute()
const clipboard = useClipboard()
const activeOS = ref('windows')
const loading = ref(true)
const cmd = ref<InstallExecutor | null>(null)

const osList = [
  { id: 'windows', label: 'Windows' },
  { id: 'linux', label: 'Linux' },
  { id: 'macos', label: 'macOS' },
]

// Terminal opening step per OS (prepended client-side)
const terminalStep: Record<string, InstallOption> = {
  windows: { label: 'Ouvrir un terminal', note: 'Appuyez sur <kbd class="bg-gray-100 dark:bg-gray-800 px-1.5 py-0.5 rounded text-xs font-mono">Win + R</kbd>, tapez <code class="bg-gray-100 dark:bg-gray-800 px-1 rounded text-xs">powershell</code> puis Entree.', noNumber: true },
  linux: { label: 'Ouvrir un terminal', note: 'Appuyez sur <kbd class="bg-gray-100 dark:bg-gray-800 px-1.5 py-0.5 rounded text-xs font-mono">Ctrl + Alt + T</kbd> ou cherchez « Terminal ».', noNumber: true },
  macos: { label: 'Ouvrir un terminal', note: 'Appuyez sur <kbd class="bg-gray-100 dark:bg-gray-800 px-1.5 py-0.5 rounded text-xs font-mono">Cmd + Espace</kbd>, tapez Terminal puis Entree.', noNumber: true },
}

function installWithTerminal(osId: string): InstallOption[] {
  // Try content elements first (new format), fallback to legacy install field
  let base: InstallOption[] = []
  if (cmd.value?.content?.length) {
    const osInstall = cmd.value.content.find((el) => el.type === 'os-install')
    if (osInstall) base = osInstall.props?.install?.[osId] || []
  } else {
    base = cmd.value?.install?.[osId] || []
  }
  return [terminalStep[osId]!, ...base]
}

const osTabs = computed(() =>
  osList.map(os => ({
    label: os.label,
    value: os.id,
    count: installWithTerminal(os.id).length,
  }))
)

async function loadExecutor() {
  loading.value = true
  try {
    cmd.value = await installGuidesPublicApi.getExecutor(route.params.slug as string)
  } catch {
    cmd.value = null
  } finally {
    loading.value = false
  }
}

onMounted(loadExecutor)

watch(() => route.params.slug, () => {
  activeOS.value = 'windows'
  loadExecutor()
})

function handleCopy(code: string) {
  clipboard.copy(code, 'Commande')
}

function stepNumber(options: InstallOption[], index: number): number {
  let n = 0
  for (let i = 0; i <= index; i++) {
    if (!options[i]?.noNumber) n++
  }
  return n
}
</script>
