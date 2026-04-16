<template>
  <div class="border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden">
    <div class="overflow-x-auto max-h-64">
      <table class="min-w-full text-sm">
        <thead class="bg-gray-50 dark:bg-gray-800 sticky top-0">
          <tr>
            <th
              v-for="header in headers"
              :key="header"
              class="px-3 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider whitespace-nowrap"
            >
              {{ header }}
            </th>
          </tr>
        </thead>
        <tbody class="divide-y divide-gray-100 dark:divide-gray-800">
          <tr
            v-for="(row, i) in rows"
            :key="i"
            class="hover:bg-gray-50 dark:hover:bg-gray-800/50"
          >
            <td
              v-for="(cell, j) in row"
              :key="j"
              class="px-3 py-2 text-gray-700 dark:text-gray-300 whitespace-nowrap max-w-[200px] truncate"
              :title="cell"
            >
              {{ cell || '—' }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <div class="px-3 py-2 bg-gray-50 dark:bg-gray-800 text-xs text-gray-500 dark:text-gray-400 border-t border-gray-200 dark:border-gray-700">
      {{ totalRows }} ligne(s) au total ({{ rows.length }} affichée(s))
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  headers: string[]
  rows: string[][]
  totalRows: number
}>()
</script>
