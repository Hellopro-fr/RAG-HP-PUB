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
      <span class="text-gray-600 dark:text-gray-300">{{ cfg?.label || '...' }}</span>
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
      </div>
      <div class="space-y-4">
        <div v-for="i in 4" :key="i" class="flex gap-3">
          <div class="flex-shrink-0 w-7 h-7 rounded-full bg-gray-200 dark:bg-gray-800" />
          <div class="flex-1 pt-0.5">
            <div class="h-4 w-1/4 rounded bg-gray-200 dark:bg-gray-800 mb-2" />
            <div class="h-3 w-5/6 rounded bg-gray-100 dark:bg-gray-800" />
          </div>
        </div>
      </div>
    </div>

    <!-- Not found -->
    <div v-else-if="!cfg" class="text-center py-16">
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

    <!-- Config content -->
    <div v-else>
      <!-- Header -->
      <div class="mb-8">
        <div class="flex items-center gap-4">
          <div
            class="w-12 h-12 rounded-lg flex items-center justify-center"
            :class="cfg.color"
          >
            <i class="pi text-xl" :class="cfg.icon" />
          </div>
          <div>
            <h1 class="text-2xl font-bold text-gray-900 dark:text-white">{{ cfg.label }}</h1>
            <p class="text-sm text-gray-500 dark:text-gray-400">{{ cfg.description }}</p>
          </div>
        </div>
      </div>

      <!-- Dynamic steps -->
      <section class="mb-8">
        <div class="space-y-4">
          <div
            v-for="(step, i) in cfg.content"
            :key="i"
            class="flex gap-3"
          >
            <span class="flex-shrink-0 w-7 h-7 rounded-full bg-brand-500 text-white text-sm font-semibold flex items-center justify-center">
              {{ i + 1 }}
            </span>
            <div class="pt-0.5 flex-1 min-w-0">
              <p class="font-medium text-gray-900 dark:text-white text-sm">{{ step.title }}</p>
              <p v-if="step.description" class="text-sm text-gray-600 dark:text-gray-400 mt-0.5" v-safe-html="step.description" />

              <!-- Executor selector (cards) -->
              <div v-if="step.hasExecutorSelector && executors.length" class="grid grid-cols-1 sm:grid-cols-2 gap-2 mt-3">
                <button
                  v-for="exec in executors"
                  :key="exec.slug"
                  type="button"
                  class="group relative text-left rounded-lg border p-3 transition-colors"
                  :class="selectedExecutor === exec.slug
                    ? 'border-brand-500 bg-brand-50/50 dark:bg-brand-500/10 dark:border-brand-400'
                    : 'border-gray-200 dark:border-gray-700 hover:border-gray-400 dark:hover:border-gray-500 bg-white dark:bg-gray-900'"
                  @click="selectedExecutor = exec.slug"
                >
                  <div class="flex items-start gap-2">
                    <div
                      v-if="exec.icon"
                      class="shrink-0 w-8 h-8 rounded-md flex items-center justify-center"
                      :class="exec.color || 'bg-gray-100 dark:bg-gray-800 text-gray-500'"
                    >
                      <i class="pi text-sm" :class="exec.icon" />
                    </div>
                    <div class="min-w-0 flex-1">
                      <div class="flex items-center gap-1.5">
                        <span class="text-sm font-semibold text-gray-900 dark:text-white truncate">{{ exec.label }}</span>
                        <span v-if="exec.sub" class="text-[11px] text-gray-500 dark:text-gray-400 truncate">{{ exec.sub }}</span>
                      </div>
                      <p
                        v-if="exec.description"
                        class="text-[11px] text-gray-600 dark:text-gray-400 mt-0.5 line-clamp-2"
                      >{{ exec.description }}</p>
                    </div>
                    <i
                      v-if="selectedExecutor === exec.slug"
                      class="pi pi-check-circle text-brand-500 text-base shrink-0"
                    />
                  </div>
                  <a
                    :href="`/install-guide/${exec.slug}`"
                    target="_blank"
                    rel="noopener noreferrer"
                    class="absolute bottom-2 right-2 inline-flex items-center gap-1 text-[10px] font-medium text-gray-400 hover:text-brand-500 dark:text-gray-500 dark:hover:text-brand-400 opacity-0 group-hover:opacity-100 transition-opacity"
                    :class="selectedExecutor === exec.slug ? 'opacity-100' : ''"
                    title="Voir le guide d'installation"
                    @click.stop
                  >
                    Guide <i class="pi pi-external-link text-[9px]" />
                  </a>
                </button>
              </div>

              <!-- Code from executor field (cli_add_cmd, mcp_config) -->
              <div v-if="step.codeField && selectedExec" class="mt-2">
                <CodeBlock :code="resolveValue(getExecutorCode(selectedExec, step.codeField))" @copy="handleCopy" />
                <!-- Note for mcp_config -->
                <div
                  v-if="step.codeField === 'mcp_config' && getExecutorNote(selectedExec).text"
                  class="mt-3 rounded-lg p-3 text-sm"
                  :class="getExecutorNote(selectedExec).class"
                >
                  <strong>{{ getExecutorNote(selectedExec).label }}</strong> <span v-safe-html="getExecutorNote(selectedExec).text" />
                </div>
              </div>

              <!-- Static code -->
              <div v-else-if="step.code" class="mt-2">
                <CodeBlock :code="resolveValue(step.code)" @copy="handleCopy" />
              </div>

              <!-- Table -->
              <div v-if="step.table && step.table.length" class="mt-3 rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden">
                <table class="w-full text-sm">
                  <tbody>
                    <tr
                      v-for="(row, j) in step.table"
                      :key="j"
                      :class="j < step.table.length - 1 ? 'border-b border-gray-100 dark:border-gray-700' : ''"
                    >
                      <td class="px-4 py-2.5 font-medium text-gray-700 dark:text-gray-300 bg-gray-50 dark:bg-gray-800/50 whitespace-nowrap w-1/3">{{ row.field }}</td>
                      <td class="px-4 py-2.5 text-gray-600 dark:text-gray-400">
                        <code v-if="resolveValue(row.value).startsWith('http')" class="bg-gray-100 dark:bg-gray-800 px-1.5 py-0.5 rounded text-xs">{{ resolveValue(row.value) }}</code>
                        <span v-else>{{ resolveValue(row.value) }}</span>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import CodeBlock from '@/components/shared/CodeBlock.vue'
import CrossSectionLink from '@/components/shared/CrossSectionLink.vue'
import { useClipboard } from '@/composables/useClipboard'
import { installGuidesPublicApi } from '@/api/install-guides'
import type { InstallExecutor, InstallConfig, ExecutorElement } from '@/types/install-guide'

const route = useRoute()
const clipboard = useClipboard()

const loading = ref(true)
const cfg = ref<InstallConfig | null>(null)
const executors = ref<InstallExecutor[]>([])
const selectedExecutor = ref('')

const selectedExec = computed(() =>
  executors.value.find(e => e.slug === selectedExecutor.value)
)

onMounted(async () => {
  try {
    const [cfgData, execData] = await Promise.all([
      installGuidesPublicApi.getConfig(route.params.slug as string),
      installGuidesPublicApi.listExecutors(),
    ])
    cfg.value = cfgData
    executors.value = execData || []
    if (executors.value.length) {
      selectedExecutor.value = executors.value[0]!.slug
    }
  } catch {
    cfg.value = null
  } finally {
    loading.value = false
  }
})

function handleCopy(code: string) {
  clipboard.copy(code, 'Commande')
}

const TYPE_BY_FIELD: Record<string, ExecutorElement['type']> = {
  mcp_config: 'mcp-config',
  cli_add_cmd: 'cli-command',
}

function getExecutorCode(exec: InstallExecutor | null | undefined, field: string | undefined): string {
  if (!exec || !field) return ''
  // Prefer dedicated top-level field (authoritative source)
  const top = (exec as unknown as Record<string, string | undefined>)[field]
  if (top) return top
  // Fall back to page-builder `content` array
  if (Array.isArray(exec.content)) {
    const elType = TYPE_BY_FIELD[field]
    if (elType) {
      const el = exec.content.find((e) => e?.type === elType)
      if (el?.props?.code) return el.props.code
    }
  }
  return ''
}

function getExecutorNote(exec: InstallExecutor | null | undefined): { label: string; text: string; class: string } {
  if (!exec) return { label: '', text: '', class: '' }
  // Prefer a `note` element inside content (page-builder source of truth)
  if (Array.isArray(exec.content)) {
    const noteEl = exec.content.find((e) => e?.type === 'note')
    if (noteEl?.props && (noteEl.props.text || noteEl.props.label)) {
      return {
        label: noteEl.props.label || '',
        text: noteEl.props.text || '',
        class: noteEl.props.class || '',
      }
    }
  }
  // Fall back to legacy fields
  return {
    label: exec.note_label || '',
    text: exec.note_text || '',
    class: exec.note_class || '',
  }
}

function resolveValue(val: string): string {
  if (!val) return ''
  const origin = window.location.origin
  const host = origin.replace(/^https?:\/\//, '')
  return val
    .replace(/https?:\/\/<gateway-url>/g, origin)
    .replace(/https?:\/\/&lt;gateway-url&gt;/g, origin)
    .replace(/<gateway-url>/g, host)
    .replace(/&lt;gateway-url&gt;/g, host)
    // <server-name> and <token> are kept literal in public docs — users
    // replace them with their own values from the token panel.
}
</script>
