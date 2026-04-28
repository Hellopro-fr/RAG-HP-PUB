<template>
  <div>
    <PageBreadcrumb page-title="Tables BDD Hellopro" />

    <PageHeaderTabs
      v-model="activeTab"
      :tabs="tabs"
    >
      <template #actions>
        <button
          v-if="authStore.isAdmin"
          class="px-4 py-2 text-sm font-medium text-white bg-brand-500 rounded-md hover:bg-brand-600"
          @click="goToCreate"
        >
          <i class="pi pi-plus mr-1" />
          Ajouter une table
        </button>
      </template>

      <!-- Filter bar -->
      <div class="mb-4">
        <input
          v-model="search"
          type="text"
          placeholder="Rechercher par nom ou description"
          class="h-10 w-full max-w-md rounded-lg border border-gray-300 bg-transparent px-4 py-2 text-sm text-gray-800 shadow-theme-xs placeholder:text-gray-400 focus:border-brand-300 focus:outline-hidden focus:ring-3 focus:ring-brand-500/10 dark:border-gray-700 dark:bg-gray-900 dark:text-white/90 dark:placeholder:text-white/30"
        />
      </div>

      <!-- Loading -->
      <div v-if="loading" class="text-center py-12">
        <i class="pi pi-spinner pi-spin text-2xl text-brand-500" />
      </div>

      <!-- Empty state -->
      <div
        v-else-if="total === 0"
        class="text-center py-12 text-gray-500 dark:text-gray-400"
      >
        <i class="pi pi-database text-4xl mb-3 block" />
        <p>Aucune table enregistree pour cet onglet.</p>
      </div>

      <!-- Table -->
      <div v-else class="overflow-x-auto">
        <table class="min-w-full text-sm">
          <thead class="sticky top-0 bg-gray-50 dark:bg-gray-800/60">
            <tr class="text-left text-xs font-semibold uppercase text-gray-500 dark:text-gray-400">
              <th class="px-3 py-2">Nom de la table</th>
              <th class="px-3 py-2">Base</th>
              <th class="px-3 py-2">Statut</th>
              <th class="px-3 py-2">Champs</th>
              <th class="px-3 py-2">Description</th>
              <th class="px-3 py-2">Ajoutee le</th>
              <th class="px-3 py-2 text-right">Actions</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-100 dark:divide-gray-800">
            <tr
              v-for="table in tables"
              :key="table.id"
              class="hover:bg-gray-50 dark:hover:bg-white/5 cursor-pointer"
              @click="goToFields(table)"
            >
              <td class="px-3 py-2 font-mono text-gray-900 dark:text-white">
                {{ table.table_name }}
              </td>
              <td class="px-3 py-2 text-gray-600 dark:text-gray-300">
                {{ databaseName(table.database_id) }}
              </td>
              <td class="px-3 py-2">
                <span
                  v-if="table.fields.length > 0"
                  class="inline-flex items-center rounded-full bg-success-50 px-2 py-0.5 text-xs font-medium text-success-700 dark:bg-success-500/15 dark:text-success-400"
                >
                  Actif
                </span>
                <div v-else>
                  <span
                    class="inline-flex items-center rounded-full bg-warning-50 px-2 py-0.5 text-xs font-medium text-warning-700 dark:bg-warning-500/15 dark:text-warning-400"
                  >
                    Non actif
                  </span>
                  <p class="text-xs text-gray-500 mt-1">
                    Ajouter des champs pour activer la table.
                  </p>
                </div>
              </td>
              <td class="px-3 py-2 text-gray-600 dark:text-gray-300">
                {{ table.fields.length }}
              </td>
              <td class="px-3 py-2 text-gray-700 dark:text-gray-300 max-w-sm truncate">
                <span v-if="table.description">{{ table.description }}</span>
                <span v-else class="text-gray-400">—</span>
              </td>
              <td class="px-3 py-2 text-gray-500 dark:text-gray-400 whitespace-nowrap">
                {{ formatDate(table.created_at) }}
              </td>
              <td class="px-3 py-2 text-right" @click.stop>
                <button
                  v-if="authStore.isAdmin"
                  type="button"
                  class="p-1.5 rounded text-error-600 dark:text-error-400 hover:bg-error-50 dark:hover:bg-error-500/10"
                  title="Supprimer"
                  @click="deletingTable = table"
                >
                  <i class="pi pi-trash" />
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Pagination -->
      <Paginator
        v-if="!loading && total > limit"
        :page="page"
        :limit="limit"
        :total="total"
        @update:page="page = $event"
      />
    </PageHeaderTabs>

    <!-- Delete table confirm -->
    <ConfirmDialog
      :open="!!deletingTable"
      title="Supprimer la table"
      message="Cette action est irreversible. La table et ses champs seront retires du registre."
      confirm-label="Supprimer"
      @update:open="deletingTable = undefined"
      @confirm="confirmDeleteTable"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { bddApi } from '@/api/bdd';
import { HELLOPRO_DATABASES } from '@/types/bdd';
import type { BDDUsedTable } from '@/types/bdd';
import { useAuthStore } from '@/stores/auth';
import { useToast } from '@/composables/useToast';
import { ApiError } from '@/types/api';
import PageBreadcrumb from '@/components/common/PageBreadcrumb.vue';
import PageHeaderTabs from '@/components/common/PageHeaderTabs.vue';
import Paginator from '@/components/common/Paginator.vue';
import ConfirmDialog from '@/components/shared/ConfirmDialog.vue';

const ALL_TAB = 'all';
const PAGE_LIMIT = 20;

const route = useRoute();
const router = useRouter();
const authStore = useAuthStore();
const toast = useToast();

const tables = ref<BDDUsedTable[]>([]);
const total = ref(0);
const loading = ref(false);
const limit = ref(PAGE_LIMIT);
const page = ref(1);
const search = ref('');

const activeTab = ref<string>(parseInitialTab());

const counts = ref<Record<string, number>>({ [ALL_TAB]: 0 });

const deletingTable = ref<BDDUsedTable | undefined>();

let searchDebounceTimer: ReturnType<typeof setTimeout> | undefined;
const debouncedSearch = ref('');

const tabs = computed(() => [
  { label: 'Toutes', value: ALL_TAB, count: counts.value[ALL_TAB] ?? 0 },
  ...HELLOPRO_DATABASES.map((d) => ({
    label: d.name,
    value: d.slug,
    count: counts.value[d.slug] ?? 0,
  })),
]);

function parseInitialTab(): string {
  const raw = String(route.query.db || '');
  if (!raw) return ALL_TAB;
  if (raw === ALL_TAB) return ALL_TAB;
  const byId = HELLOPRO_DATABASES.find((d) => String(d.id) === raw);
  if (byId) return byId.slug;
  const bySlug = HELLOPRO_DATABASES.find((d) => d.slug === raw);
  if (bySlug) return bySlug.slug;
  return ALL_TAB;
}

function activeDatabaseId(): number | undefined {
  if (activeTab.value === ALL_TAB) return undefined;
  return HELLOPRO_DATABASES.find((d) => d.slug === activeTab.value)?.id;
}

function databaseName(id: number): string {
  return HELLOPRO_DATABASES.find((d) => d.id === id)?.name || '—';
}

function formatDate(d?: string): string {
  if (!d) return '—';
  try {
    return new Date(d).toLocaleDateString('fr-FR', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
    });
  } catch {
    return d;
  }
}

async function loadTables() {
  loading.value = true;
  try {
    const res = await bddApi.listUsed({
      database_id: activeDatabaseId(),
      search: debouncedSearch.value || undefined,
      page: page.value,
      limit: limit.value,
    });
    tables.value = res.tables || [];
    total.value = res.total ?? 0;
  } catch (err) {
    if (err instanceof ApiError && err.status === 503) {
      toast.error('Service BDD indisponible');
    } else {
      toast.error('Impossible de charger les tables');
    }
    tables.value = [];
    total.value = 0;
  } finally {
    loading.value = false;
  }
}

async function loadCounts() {
  try {
    const allRes = await bddApi.listUsed({ page: 1, limit: 1 });
    const next: Record<string, number> = { [ALL_TAB]: allRes.total ?? 0 };
    const perDb = await Promise.all(
      HELLOPRO_DATABASES.map(async (d) => {
        try {
          const res = await bddApi.listUsed({ database_id: d.id, page: 1, limit: 1 });
          return { slug: d.slug, total: res.total ?? 0 };
        } catch {
          return { slug: d.slug, total: 0 };
        }
      }),
    );
    for (const r of perDb) next[r.slug] = r.total;
    counts.value = next;
  } catch {
    // Silent — list view will still load; counts stay at zero.
  }
}

onMounted(async () => {
  await Promise.all([loadCounts(), loadTables()]);
});

watch(activeTab, (next) => {
  page.value = 1;
  router.replace({ query: { ...route.query, db: next } });
});

watch(search, (value) => {
  if (searchDebounceTimer) clearTimeout(searchDebounceTimer);
  searchDebounceTimer = setTimeout(() => {
    debouncedSearch.value = value.trim();
  }, 300);
});

watch(debouncedSearch, () => {
  page.value = 1;
});

watch([activeTab, page, debouncedSearch], () => {
  loadTables();
});

function goToCreate() {
  router.push('/bdd-tables/new');
}

function goToFields(table: BDDUsedTable) {
  router.push('/bdd-tables/' + table.id + '/fields');
}

async function confirmDeleteTable() {
  if (!deletingTable.value) return;
  const target = deletingTable.value;
  try {
    await bddApi.deleteUsed(target.id);
    toast.success('Table supprimee');
    await Promise.all([loadCounts(), loadTables()]);
  } catch {
    toast.error('Impossible de supprimer la table');
  } finally {
    deletingTable.value = undefined;
  }
}
</script>
