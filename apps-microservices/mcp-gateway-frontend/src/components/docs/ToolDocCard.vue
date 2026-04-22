<template>
  <div class="rounded-lg border border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-900">
    <div class="p-5 border-b border-gray-100 dark:border-gray-800">
      <h3 class="text-base font-semibold text-gray-900 dark:text-white font-mono">
        {{ tool.name }}
      </h3>
      <p v-if="tool.description" class="mt-1 text-sm text-gray-600 dark:text-gray-400 whitespace-pre-line">
        {{ truncate(tool.description, showFullDesc) }}<button
          v-if="isLong(tool.description)"
          type="button"
          class="ml-1 text-xs font-medium text-brand-500 hover:text-brand-600 dark:text-brand-400 inline-flex items-center gap-0.5"
          @click="showFullDesc = !showFullDesc"
        >
          {{ showFullDesc ? 'Voir moins' : 'Voir plus' }}
          <i :class="showFullDesc ? 'pi pi-chevron-up' : 'pi pi-chevron-down'" class="text-[9px]" />
        </button>
      </p>
    </div>
    <div class="p-5">
      <div v-if="flatProperties.length > 0">
        <h4 class="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-3">
          Parametres
        </h4>
        <div class="overflow-x-auto">
          <table class="w-full text-sm">
            <thead>
              <tr class="text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                <th class="pb-2 pr-4">Nom</th>
                <th class="pb-2 pr-4">Type</th>
                <th class="pb-2 pr-4">Requis</th>
                <th class="pb-2">Description</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-gray-100 dark:divide-gray-800">
              <tr v-for="prop in flatProperties" :key="prop.name">
                <td class="py-2 pr-4 align-top">
                  <code
                    class="text-sm font-mono"
                    :class="[prop.depth > 0 ? 'text-gray-500 dark:text-gray-400' : 'text-gray-900 dark:text-white']"
                    :style="{ paddingLeft: `${prop.depth * 16}px` }"
                  >
                    <span v-if="prop.depth > 0" class="text-gray-300 dark:text-gray-600 mr-1">&#8627;</span>
                    {{ prop.displayName }}
                  </code>
                </td>
                <td class="py-2 pr-4 align-top">
                  <span class="inline-block px-1.5 py-0.5 text-xs font-mono rounded bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300">
                    {{ prop.type }}
                  </span>
                </td>
                <td class="py-2 pr-4 align-top">
                  <span
                    v-if="prop.required"
                    class="inline-block px-1.5 py-0.5 text-xs font-medium rounded bg-red-50 text-red-600 dark:bg-red-900/30 dark:text-red-400"
                  >
                    Oui
                  </span>
                  <span v-else class="text-xs text-gray-400">Non</span>
                </td>
                <td class="py-2 align-top text-gray-600 dark:text-gray-400">
                  <div class="whitespace-pre-line">
                    {{ truncate(prop.description, expandedProps.has(prop.name)) }}
                  </div>
                  <button
                    v-if="isLong(prop.description)"
                    type="button"
                    class="mt-1 text-xs font-medium text-brand-500 hover:text-brand-600 dark:text-brand-400 inline-flex items-center gap-0.5"
                    @click="toggleProp(prop.name)"
                  >
                    {{ expandedProps.has(prop.name) ? 'Voir moins' : 'Voir plus' }}
                    <i :class="expandedProps.has(prop.name) ? 'pi pi-chevron-up' : 'pi pi-chevron-down'" class="text-[9px]" />
                  </button>
                  <div v-if="prop.enumValues" class="mt-1 text-xs text-gray-500 dark:text-gray-500">
                    <span class="font-medium">Valeurs :</span>
                    <span v-if="expandedEnums.has(prop.name)">{{ prop.enumValues.join(', ') }}</span>
                    <span v-else>{{ truncateList(prop.enumValues) }}</span>
                    <button
                      v-if="prop.enumValues.length > MAX_ENUM_PREVIEW"
                      type="button"
                      class="ml-1 font-medium text-brand-500 hover:text-brand-600 dark:text-brand-400 inline-flex items-center gap-0.5"
                      @click="toggleEnum(prop.name)"
                    >
                      {{ expandedEnums.has(prop.name) ? 'Voir moins' : `Voir plus (${prop.enumValues.length - MAX_ENUM_PREVIEW})` }}
                      <i :class="expandedEnums.has(prop.name) ? 'pi pi-chevron-up' : 'pi pi-chevron-down'" class="text-[9px]" />
                    </button>
                  </div>
                  <span v-if="prop.defaultValue !== undefined" class="block mt-0.5 text-xs text-gray-500 dark:text-gray-500">
                    Defaut : <code class="font-mono">{{ prop.defaultValue }}</code>
                  </span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
      <div v-else-if="hasSchema" class="text-sm text-gray-500 dark:text-gray-400">
        <h4 class="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-3">
          Schema
        </h4>
        <pre class="p-3 rounded-lg bg-gray-50 dark:bg-gray-800 text-xs font-mono overflow-x-auto">{{ formattedSchema }}</pre>
      </div>
      <p v-else class="text-sm text-gray-400 dark:text-gray-500 italic">
        Aucun parametre
      </p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, reactive } from 'vue';
import type { PublicToolDetail, JsonSchema, JsonSchemaProperty } from '@/types/public';

const props = defineProps<{
  tool: PublicToolDetail
}>();

// Truncate threshold — descriptions shorter than this never show the toggle.
const MAX_PREVIEW = 200
// How many enum values to show before collapsing the "Valeurs" list.
const MAX_ENUM_PREVIEW = 10
const showFullDesc = ref(false)
const expandedProps = reactive(new Set<string>())
const expandedEnums = reactive(new Set<string>())

function isLong(s?: string): boolean {
  return !!s && s.length > MAX_PREVIEW
}

function truncate(s: string | undefined, expanded: boolean): string {
  if (!s) return ''
  if (expanded || !isLong(s)) return s
  // Cut at word boundary close to MAX_PREVIEW for a cleaner look
  const slice = s.slice(0, MAX_PREVIEW)
  const lastSpace = slice.lastIndexOf(' ')
  const cutoff = lastSpace > MAX_PREVIEW * 0.6 ? lastSpace : MAX_PREVIEW
  return s.slice(0, cutoff) + '…'
}

function toggleProp(name: string) {
  if (expandedProps.has(name)) expandedProps.delete(name)
  else expandedProps.add(name)
}

function toggleEnum(name: string) {
  if (expandedEnums.has(name)) expandedEnums.delete(name)
  else expandedEnums.add(name)
}

function truncateList(list: string[]): string {
  if (list.length <= MAX_ENUM_PREVIEW) return list.join(', ')
  return list.slice(0, MAX_ENUM_PREVIEW).join(', ') + ', …'
}

interface FlatProperty {
  name: string
  displayName: string
  type: string
  required: boolean
  description: string
  depth: number
  enumValues?: string[]
  defaultValue?: string
}

function resolveType(prop: JsonSchemaProperty): string {
  if (Array.isArray(prop.type)) return prop.type.join(' | ')
  if (prop.enum) return `enum`
  if (prop.type === 'array' && prop.items) return `${resolveType(prop.items)}[]`
  if (prop.oneOf) return prop.oneOf.map(resolveType).join(' | ')
  if (prop.anyOf) return prop.anyOf.map(resolveType).join(' | ')
  return prop.type || 'any'
}

function flattenSchema(
  schema: JsonSchema,
  requiredList: string[],
  depth: number = 0,
  prefix: string = ''
): FlatProperty[] {
  const result: FlatProperty[] = []
  if (!schema.properties) return result

  for (const [name, prop] of Object.entries(schema.properties)) {
    const fullName = prefix ? `${prefix}.${name}` : name
    const isRequired = requiredList.includes(name)

    result.push({
      name: fullName,
      displayName: name,
      type: resolveType(prop),
      required: isRequired,
      description: prop.description || '',
      depth,
      enumValues: prop.enum?.map(String),
      defaultValue: prop.default !== undefined ? String(prop.default) : undefined,
    })

    if (prop.type === 'object' && prop.properties && depth < 3) {
      result.push(...flattenSchema(
        prop as JsonSchema,
        prop.required || [],
        depth + 1,
        fullName
      ))
    }

    if (prop.type === 'array' && prop.items?.type === 'object' && prop.items.properties && depth < 3) {
      result.push(...flattenSchema(
        prop.items as JsonSchema,
        prop.items.required || [],
        depth + 1,
        `${fullName}[]`
      ))
    }
  }
  return result
}

const schema = computed<JsonSchema | null>(() => {
  try {
    const s = props.tool.input_schema
    if (!s || typeof s !== 'object') return null
    return s as JsonSchema
  } catch {
    return null
  }
})

const flatProperties = computed<FlatProperty[]>(() => {
  if (!schema.value?.properties) return []
  return flattenSchema(schema.value, schema.value.required || [])
})

const hasSchema = computed(() => {
  return schema.value && Object.keys(schema.value).length > 0
})

const formattedSchema = computed(() => {
  try {
    return JSON.stringify(props.tool.input_schema, null, 2)
  } catch {
    return '{}'
  }
})
</script>
