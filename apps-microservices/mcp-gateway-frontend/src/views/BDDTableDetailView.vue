<template>
  <div>
    <!-- Page header -->
    <div class="mb-6 flex items-center gap-4">
      <button
        type="button"
        class="inline-flex items-center gap-1.5 text-sm text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white"
        @click="router.push('/bdd-tables')"
      >
        <i class="pi pi-arrow-left text-xs" />
        Retour
      </button>
      <h1 class="text-2xl font-bold text-gray-900 dark:text-white">
        {{ table?.table_name || 'Detail de la table' }}
      </h1>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="text-center py-12">
      <i class="pi pi-spinner pi-spin text-2xl text-brand-500" />
    </div>

    <!-- Not found -->
    <div
      v-else-if="!table"
      class="rounded-2xl border border-gray-200 bg-white dark:border-gray-800 dark:bg-white/[0.03] p-10 text-center"
    >
      <i class="pi pi-exclamation-triangle text-3xl text-warning-500 mb-3 block" />
      <p class="text-sm text-gray-700 dark:text-gray-300 mb-4">
        Table introuvable.
      </p>
      <router-link
        to="/bdd-tables"
        class="inline-flex items-center gap-1.5 text-sm font-medium text-brand-500 hover:text-brand-600"
      >
        <i class="pi pi-arrow-left text-xs" />
        Retour a la liste des tables
      </router-link>
    </div>

    <!-- Detail -->
    <div
      v-else
      class="rounded-2xl border border-gray-200 bg-white dark:border-gray-800 dark:bg-white/[0.03]"
    >
      <header
        class="flex flex-wrap items-start justify-between gap-3 border-b border-gray-100 px-6 py-5 dark:border-gray-800"
      >
        <div class="min-w-0">
          <p class="text-xs uppercase tracking-wide text-gray-500 dark:text-gray-400">
            {{ databaseName(table.database_id) }}
          </p>
          <p class="mt-1 font-mono text-sm text-gray-700 dark:text-gray-300 truncate">
            {{ table.table_name }}
          </p>
        </div>
        <div class="flex items-center gap-2 shrink-0">
          <span
            v-if="!table.is_active"
            class="inline-flex items-center rounded-full bg-gray-100 dark:bg-gray-700 px-2.5 py-0.5 text-xs font-medium text-gray-600 dark:text-gray-300"
          >
            Inactive
          </span>
          <span
            v-else-if="hasFields"
            class="inline-flex items-center rounded-full bg-success-50 px-2.5 py-0.5 text-xs font-medium text-success-700 dark:bg-success-500/15 dark:text-success-400"
          >
            <i class="pi pi-check-circle text-[10px] mr-1" />
            Active
          </span>
          <span
            v-else
            class="inline-flex items-center rounded-full bg-warning-50 px-2.5 py-0.5 text-xs font-medium text-warning-700 dark:bg-warning-500/15 dark:text-warning-400"
          >
            Brouillon
          </span>
          <router-link
            v-if="authStore.isAdmin"
            :to="'/bdd-tables/' + table.id + '/fields'"
            class="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-white bg-brand-500 rounded-md hover:bg-brand-600"
          >
            <i class="pi pi-pencil text-[10px]" />
            Editer
          </router-link>
        </div>
      </header>

      <!-- Stat strip -->
      <section class="grid grid-cols-2 gap-px bg-gray-100 dark:bg-gray-800 sm:grid-cols-4">
        <div class="bg-white dark:bg-transparent px-4 py-3">
          <div class="flex items-center justify-between gap-2">
            <p class="text-xs uppercase tracking-wide text-gray-500 dark:text-gray-400">
              Lignes
            </p>
            <button
              v-if="authStore.isAdmin"
              type="button"
              :disabled="refreshingRows"
              class="p-1 rounded text-gray-500 hover:text-brand-600 hover:bg-brand-50 dark:hover:bg-brand-500/10 disabled:opacity-50"
              :title="refreshError || 'Rafraichir le compte depuis le catalogue'"
              @click="refreshRows"
            >
              <i :class="refreshingRows ? 'pi pi-spinner pi-spin' : 'pi pi-refresh'" class="text-xs" />
            </button>
          </div>
          <p class="mt-1 text-sm font-mono text-gray-900 dark:text-white">
            {{ table.rows !== null && table.rows !== undefined ? formatRows(table.rows) : '—' }}
          </p>
          <p v-if="refreshError" class="mt-1 text-xs text-error-500 truncate" :title="refreshError">
            {{ refreshError }}
          </p>
        </div>
        <div class="bg-white dark:bg-transparent px-4 py-3">
          <p class="text-xs uppercase tracking-wide text-gray-500 dark:text-gray-400">
            Cle primaire
          </p>
          <p class="mt-1 text-sm font-mono text-gray-900 dark:text-white truncate">
            {{ table.primary_key || '—' }}
          </p>
        </div>
        <div class="bg-white dark:bg-transparent px-4 py-3">
          <p class="text-xs uppercase tracking-wide text-gray-500 dark:text-gray-400">
            Ordre par defaut
          </p>
          <p class="mt-1 text-sm font-mono text-gray-900 dark:text-white truncate">
            {{ table.default_order_by || '—' }}
          </p>
        </div>
        <div class="bg-white dark:bg-transparent px-4 py-3">
          <p class="text-xs uppercase tracking-wide text-gray-500 dark:text-gray-400">
            Champs
          </p>
          <p class="mt-1 text-sm font-mono text-gray-900 dark:text-white">
            {{ table.fields.length }}
          </p>
        </div>
      </section>

      <!-- Description -->
      <section class="px-6 py-5 border-t border-gray-100 dark:border-gray-800">
        <h2 class="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
          Description
        </h2>
        <p
          v-if="table.description"
          class="whitespace-pre-line text-sm text-gray-700 dark:text-gray-300"
        >
          {{ plainDescription }}
        </p>
        <p v-else class="text-sm text-gray-400">
          Aucune description.
        </p>
      </section>

      <!-- Notes -->
      <section
        v-if="table.notes"
        class="px-6 py-5 border-t border-gray-100 dark:border-gray-800"
      >
        <h2 class="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
          Notes
        </h2>
        <p class="whitespace-pre-line text-sm text-gray-700 dark:text-gray-300">
          {{ table.notes }}
        </p>
      </section>

      <!-- Fields -->
      <section class="px-6 py-5 border-t border-gray-100 dark:border-gray-800">
        <h2 class="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
          Champs exposes
          <span class="ml-1 text-xs text-gray-500">({{ table.fields.length }})</span>
        </h2>
        <div
          v-if="table.fields.length === 0"
          class="rounded-lg border border-dashed border-gray-200 dark:border-gray-700 px-4 py-6 text-center text-sm text-gray-500"
        >
          Aucun champ enregistre.
        </div>
        <div v-else class="overflow-x-auto">
          <table class="min-w-full text-sm">
            <thead>
              <tr
                class="text-left text-xs font-semibold uppercase text-gray-500 dark:text-gray-400 border-b border-gray-100 dark:border-gray-800"
              >
                <th class="px-3 py-2">Nom</th>
                <th class="px-3 py-2">Type</th>
                <th class="px-3 py-2">Description</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-gray-100 dark:divide-gray-800">
              <tr v-for="f in table.fields" :key="f.id">
                <td class="px-3 py-2 font-mono text-gray-900 dark:text-white">
                  {{ f.field_name }}
                  <span
                    v-if="f.field_name === table.primary_key"
                    class="ml-1 inline-flex items-center rounded bg-brand-50 px-1.5 py-0.5 text-[10px] font-medium text-brand-700 dark:bg-brand-500/15 dark:text-brand-400"
                    title="Cle primaire"
                  >
                    PK
                  </span>
                </td>
                <td class="px-3 py-2 text-gray-600 dark:text-gray-300">
                  {{ f.field_type || '—' }}
                </td>
                <td class="px-3 py-2 text-gray-700 dark:text-gray-300">
                  <span v-if="f.description">{{ stripHtml(f.description) }}</span>
                  <span v-else class="text-gray-400">—</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <!-- Relations -->
      <section
        v-if="parsedRelations.length > 0"
        class="px-6 py-5 border-t border-gray-100 dark:border-gray-800"
      >
        <h2 class="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
          Relations
          <span class="ml-1 text-xs text-gray-500">({{ parsedRelations.length }})</span>
        </h2>
        <ul class="space-y-1.5">
          <li
            v-for="(r, idx) in parsedRelations"
            :key="idx"
            class="flex items-center gap-2 text-sm font-mono text-gray-700 dark:text-gray-300"
          >
            <span class="text-gray-900 dark:text-white">{{ r.self_col || '?' }}</span>
            <i class="pi pi-arrow-right text-[10px] text-gray-400" />
            <span class="text-gray-900 dark:text-white">
              {{ r.target_table }}<span class="text-gray-400">.</span>{{ r.target_col || '?' }}
            </span>
          </li>
        </ul>
      </section>

      <!-- Footer meta -->
      <footer
        class="flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-gray-100 px-6 py-3 text-xs text-gray-500 dark:border-gray-800 dark:text-gray-400"
      >
        <span v-if="table.created_at">
          Ajoutee le {{ formatDate(table.created_at) }}
        </span>
        <span v-if="table.updated_at">
          Modifiee le {{ formatDate(table.updated_at) }}
        </span>
        <span v-if="table.created_by">
          par {{ table.created_by }}
        </span>
      </footer>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { bddApi } from '@/api/bdd';
import type { BDDUsedTable } from '@/types/bdd';
import { HELLOPRO_DATABASES } from '@/types/bdd';
import { useAuthStore } from '@/stores/auth';

const route = useRoute();
const router = useRouter();
const authStore = useAuthStore();

const id = computed(() => String(route.params.id || ''));
const table = ref<BDDUsedTable | null>(null);
const loading = ref(false);
const refreshingRows = ref(false);
const refreshError = ref<string | null>(null);

const hasFields = computed(() => (table.value?.fields.length ?? 0) > 0);

async function refreshRows() {
  if (!table.value) return;
  refreshingRows.value = true;
  refreshError.value = null;
  try {
    const updated = await bddApi.refreshCatalog(table.value.id);
    table.value = updated;
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : 'Erreur inconnue';
    refreshError.value = msg;
  } finally {
    refreshingRows.value = false;
  }
}

const RELATION_RE = /^\s*(\w+)\.(\w+)\s*->\s*(\w+)\.(\w+)\s*$/;

interface ParsedRelation {
  self_col: string;
  target_table: string;
  target_col: string;
}

const parsedRelations = computed<ParsedRelation[]>(() => {
  const value = table.value?.relations;
  if (!value || Array.isArray(value) || typeof value !== 'object') return [];
  const out: ParsedRelation[] = [];
  for (const [target, expr] of Object.entries(value as Record<string, unknown>)) {
    if (typeof expr !== 'string') continue;
    const m = expr.match(RELATION_RE);
    if (m) {
      out.push({
        self_col: m[2] ?? '',
        target_table: m[3] || target,
        target_col: m[4] ?? '',
      });
    } else {
      out.push({ self_col: '', target_table: target, target_col: '' });
    }
  }
  return out;
});

function stripHtml(html: string): string {
  const div = document.createElement('div');
  div.innerHTML = html;
  return div.textContent || div.innerText || '';
}

const plainDescription = computed(() => stripHtml(table.value?.description ?? ''));

function databaseName(dbId: number): string {
  return HELLOPRO_DATABASES.find((d) => d.id === dbId)?.name || '—';
}

function formatRows(n: number): string {
  return new Intl.NumberFormat('fr-FR').format(n);
}

function formatDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString('fr-FR', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

async function load() {
  if (!id.value) return;
  loading.value = true;
  try {
    table.value = await bddApi.getUsed(id.value);
  } catch {
    table.value = null;
  } finally {
    loading.value = false;
  }
}

watch(id, load);
onMounted(load);
</script>
