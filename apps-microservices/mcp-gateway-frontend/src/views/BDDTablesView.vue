<template>
  <div>
    <PageBreadcrumb page-title="Tables BDD Hellopro" />

    <PageHeaderTabs
      v-model="activeTab"
      :tabs="tabs"
    >
      <template #actions>
        <div v-if="authStore.isAdmin" class="flex flex-wrap items-center gap-2">
          <button
            type="button"
            class="inline-flex items-center gap-1.5 px-3 py-2 text-sm font-medium text-gray-700 dark:text-gray-200 border border-gray-300 dark:border-gray-600 rounded-md hover:bg-gray-50 dark:hover:bg-gray-700"
            @click="openMetaModal"
          >
            <i class="pi pi-cog text-xs" />
            Editer _meta
          </button>
          <button
            type="button"
            class="inline-flex items-center gap-1.5 px-3 py-2 text-sm font-medium text-gray-700 dark:text-gray-200 border border-gray-300 dark:border-gray-600 rounded-md hover:bg-gray-50 dark:hover:bg-gray-700"
            @click="openImportModal"
          >
            <i class="pi pi-upload text-xs" />
            Importer JSON
          </button>
          <button
            type="button"
            :disabled="exporting"
            class="inline-flex items-center gap-1.5 px-3 py-2 text-sm font-medium text-gray-700 dark:text-gray-200 border border-gray-300 dark:border-gray-600 rounded-md hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed"
            @click="exportRegistry"
          >
            <i
              :class="exporting ? 'pi pi-spinner pi-spin' : 'pi pi-download'"
              class="text-xs"
            />
            Exporter JSON
          </button>
          <button
            class="px-4 py-2 text-sm font-medium text-white bg-brand-500 rounded-md hover:bg-brand-600"
            @click="goToCreate"
          >
            <i class="pi pi-plus mr-1" />
            Ajouter une table
          </button>
        </div>
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

      <!-- Bulk action bar (admin) -->
      <div
        v-if="authStore.isAdmin && selectedIds.size > 0"
        class="mb-3 flex flex-wrap items-center gap-2 rounded-lg border border-brand-300 dark:border-brand-500/40 bg-brand-50 dark:bg-brand-500/10 px-3 py-2"
      >
        <span class="text-sm text-brand-800 dark:text-brand-200">
          {{ selectedIds.size }} table{{ selectedIds.size > 1 ? 's' : '' }} selectionnee{{ selectedIds.size > 1 ? 's' : '' }}
        </span>
        <span class="text-xs text-gray-400">|</span>
        <label class="text-xs font-medium text-gray-600 dark:text-gray-300">
          Deplacer vers :
        </label>
        <select
          v-model.number="bulkTargetDb"
          class="h-8 rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-2 text-xs"
        >
          <option :value="null">— base —</option>
          <option v-for="d in HELLOPRO_DATABASES" :key="d.id" :value="d.id">
            {{ d.name }}
          </option>
        </select>
        <button
          type="button"
          :disabled="bulkBusy || bulkTargetDb === null"
          class="px-2.5 py-1 text-xs font-medium text-white bg-brand-500 rounded-md hover:bg-brand-600 disabled:opacity-50 disabled:cursor-not-allowed"
          @click="applyBulkMove"
        >
          Deplacer
        </button>
        <span class="text-xs text-gray-400">|</span>
        <button
          type="button"
          :disabled="bulkBusy"
          class="px-2.5 py-1 text-xs font-medium text-success-700 dark:text-success-400 border border-success-300 dark:border-success-500/40 rounded-md hover:bg-success-50 dark:hover:bg-success-500/10 disabled:opacity-50"
          @click="applyBulkActive(true)"
        >
          <i class="pi pi-check-circle text-[10px] mr-1" />
          Activer
        </button>
        <button
          type="button"
          :disabled="bulkBusy"
          class="px-2.5 py-1 text-xs font-medium text-warning-700 dark:text-warning-400 border border-warning-300 dark:border-warning-500/40 rounded-md hover:bg-warning-50 dark:hover:bg-warning-500/10 disabled:opacity-50"
          @click="applyBulkActive(false)"
        >
          <i class="pi pi-pause text-[10px] mr-1" />
          Desactiver
        </button>
        <button
          type="button"
          :disabled="bulkBusy"
          class="px-2.5 py-1 text-xs font-medium text-error-700 dark:text-error-400 border border-error-300 dark:border-error-500/40 rounded-md hover:bg-error-50 dark:hover:bg-error-500/10 disabled:opacity-50"
          @click="bulkDeleteOpen = true"
        >
          <i class="pi pi-trash text-[10px] mr-1" />
          Supprimer
        </button>
        <button
          type="button"
          class="ml-auto px-2 py-1 text-xs text-gray-500 hover:text-gray-700 dark:hover:text-gray-200"
          @click="clearSelection"
        >
          Annuler
        </button>
      </div>

      <!-- Table -->
      <div v-if="!loading && total > 0" class="overflow-x-auto">
        <table class="min-w-full text-sm">
          <thead class="sticky top-0 bg-gray-50 dark:bg-gray-800/60">
            <tr class="text-left text-xs font-semibold uppercase text-gray-500 dark:text-gray-400">
              <th v-if="authStore.isAdmin" class="px-3 py-2 w-8">
                <input
                  type="checkbox"
                  class="rounded border-gray-300 text-brand-500"
                  :checked="allOnPageSelected"
                  :indeterminate.prop="someOnPageSelected"
                  @change="toggleSelectAll(($event.target as HTMLInputElement).checked)"
                />
              </th>
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
              <td v-if="authStore.isAdmin" class="px-3 py-2 w-8" @click.stop>
                <input
                  type="checkbox"
                  class="rounded border-gray-300 text-brand-500"
                  :checked="selectedIds.has(table.id)"
                  @change="toggleRow(table.id, ($event.target as HTMLInputElement).checked)"
                />
              </td>
              <td class="px-3 py-2 font-mono text-gray-900 dark:text-white">
                {{ table.table_name }}
              </td>
              <td class="px-3 py-2 text-gray-600 dark:text-gray-300">
                {{ databaseName(table.database_id) }}
              </td>
              <td class="px-3 py-2">
                <span
                  v-if="!table.is_active"
                  class="inline-flex items-center rounded-full bg-gray-100 dark:bg-gray-700 px-2 py-0.5 text-xs font-medium text-gray-600 dark:text-gray-300"
                >
                  Inactive
                </span>
                <span
                  v-else-if="table.fields.length > 0"
                  class="inline-flex items-center rounded-full bg-success-50 px-2 py-0.5 text-xs font-medium text-success-700 dark:bg-success-500/15 dark:text-success-400"
                >
                  Active
                </span>
                <div v-else>
                  <span
                    class="inline-flex items-center rounded-full bg-warning-50 px-2 py-0.5 text-xs font-medium text-warning-700 dark:bg-warning-500/15 dark:text-warning-400"
                  >
                    Brouillon
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

    <!-- Bulk delete confirm -->
    <ConfirmDialog
      :open="bulkDeleteOpen"
      title="Supprimer les tables selectionnees"
      :message="
        'Cette action est irreversible. ' +
        selectedIds.size +
        ' table(s) et leurs champs seront retires du registre.'
      "
      confirm-label="Supprimer"
      @update:open="bulkDeleteOpen = $event"
      @confirm="applyBulkDelete"
    />

    <!-- Import dropzone modal -->
    <div
      v-if="importOpen"
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      @click.self="closeImportModal"
    >
      <div
        class="w-full max-w-xl rounded-2xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 shadow-xl"
      >
        <header
          class="flex items-center justify-between border-b border-gray-100 dark:border-gray-800 px-5 py-4"
        >
          <div>
            <h2 class="text-base font-semibold text-gray-900 dark:text-white">
              Importer JSON
            </h2>
            <p class="text-xs text-gray-500 mt-0.5">
              Glisser-deposer un export du registre ou parcourir.
            </p>
          </div>
          <button
            type="button"
            class="p-1.5 rounded text-gray-400 hover:text-gray-600 dark:hover:text-gray-200"
            @click="closeImportModal"
          >
            <i class="pi pi-times text-sm" />
          </button>
        </header>

        <div class="px-5 py-4 space-y-4">
          <div
            class="rounded-xl border-2 border-dashed transition-colors px-6 py-10 text-center"
            :class="
              importDragOver
                ? 'border-brand-500 bg-brand-50 dark:bg-brand-500/10'
                : 'border-gray-300 dark:border-gray-700 bg-gray-50 dark:bg-gray-800/40'
            "
            @dragenter.prevent="importDragOver = true"
            @dragover.prevent="importDragOver = true"
            @dragleave.prevent="importDragOver = false"
            @drop.prevent="onImportDrop"
          >
            <div
              class="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-gray-200 dark:bg-gray-700 text-gray-500 dark:text-gray-300"
            >
              <i
                :class="importing ? 'pi pi-spinner pi-spin' : 'pi pi-upload'"
                class="text-lg"
              />
            </div>
            <p class="text-sm font-semibold text-gray-800 dark:text-gray-200">
              Glisser-deposer le fichier ici
            </p>
            <p class="text-xs text-gray-500 dark:text-gray-400 mt-1">
              Glisser-deposer un export ou une doc JSON ou
              <button
                type="button"
                class="underline text-brand-500 hover:text-brand-600 dark:text-brand-400"
                @click="importInputRef?.click()"
              >
                parcourir
              </button>
            </p>
            <input
              ref="importInputRef"
              type="file"
              accept="application/json,.json"
              class="hidden"
              @change="onImportPicked"
            />
          </div>
          <p class="text-[11px] text-gray-400">
            Formats acceptes : export du registre (`{tables:[...]}`) ou doc
            (`{_meta, table_name:{database_id, ...}}`). Pour la doc, la cle
            `database_id` portee par chaque table designe la base cible
            (1 = Hellopro BO par defaut, 5 = Data, 10 = IA).
          </p>
          <p
            v-if="importError"
            class="text-xs text-error-500"
          >
            {{ importError }}
          </p>
        </div>
      </div>
    </div>

    <!-- _meta edit modal -->
    <div
      v-if="metaOpen"
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      @click.self="closeMetaModal"
    >
      <div
        class="w-full max-w-2xl rounded-2xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 shadow-xl"
      >
        <header
          class="flex items-center justify-between border-b border-gray-100 dark:border-gray-800 px-5 py-4"
        >
          <div>
            <h2 class="text-base font-semibold text-gray-900 dark:text-white">
              Metadonnees globales (_meta)
            </h2>
            <p class="text-xs text-gray-500 mt-0.5">
              Decore l'en-tete du payload de doc consomme par bdd_get_table_doc.
            </p>
          </div>
          <button
            type="button"
            class="p-1.5 rounded text-gray-400 hover:text-gray-600 dark:hover:text-gray-200"
            @click="closeMetaModal"
          >
            <i class="pi pi-times text-sm" />
          </button>
        </header>

        <div v-if="metaLoading" class="px-5 py-8 text-center">
          <i class="pi pi-spinner pi-spin text-xl text-brand-500" />
        </div>
        <div v-else class="px-5 py-4 space-y-4">
          <div>
            <label
              class="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1"
            >
              Description
            </label>
            <textarea
              v-model="metaDraft.description"
              rows="3"
              maxlength="2048"
              placeholder="Documentation du schema de la base..."
              class="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200"
            />
          </div>
          <div>
            <label
              class="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1"
            >
              Usage
            </label>
            <textarea
              v-model="metaDraft.usage"
              rows="3"
              maxlength="2048"
              placeholder="Appeler le tool bdd_get_table_doc pour..."
              class="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200"
            />
          </div>
          <p
            v-if="meta?.updated_at"
            class="text-[11px] text-gray-400"
          >
            Derniere modification : {{ formatDateTime(meta.updated_at) }}
            <template v-if="meta.updated_by"> par {{ meta.updated_by }}</template>
          </p>
        </div>

        <footer
          class="flex items-center justify-end gap-2 border-t border-gray-100 dark:border-gray-800 px-5 py-3"
        >
          <button
            type="button"
            class="px-3 py-1.5 text-sm font-medium text-gray-700 dark:text-gray-200 border border-gray-300 dark:border-gray-600 rounded-md hover:bg-gray-50 dark:hover:bg-gray-700"
            @click="closeMetaModal"
          >
            Annuler
          </button>
          <button
            type="button"
            :disabled="metaSaving"
            class="px-4 py-1.5 text-sm font-medium text-white bg-brand-500 rounded-md hover:bg-brand-600 disabled:opacity-50 disabled:cursor-not-allowed"
            @click="saveMeta"
          >
            <i
              v-if="metaSaving"
              class="pi pi-spinner pi-spin text-xs mr-1"
            />
            Enregistrer
          </button>
        </footer>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { bddApi } from '@/api/bdd';
import { HELLOPRO_DATABASES } from '@/types/bdd';
import type { BDDUsedTable, BDDMeta } from '@/types/bdd';
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

const selectedIds = ref<Set<string>>(new Set());
const bulkTargetDb = ref<number | null>(null);
const bulkBusy = ref(false);
const bulkDeleteOpen = ref(false);

const allOnPageSelected = computed(() => {
  if (tables.value.length === 0) return false;
  return tables.value.every((t) => selectedIds.value.has(t.id));
});

const someOnPageSelected = computed(() => {
  if (tables.value.length === 0) return false;
  const has = tables.value.some((t) => selectedIds.value.has(t.id));
  return has && !allOnPageSelected.value;
});

function toggleRow(id: string, checked: boolean) {
  const next = new Set(selectedIds.value);
  if (checked) next.add(id);
  else next.delete(id);
  selectedIds.value = next;
}

function toggleSelectAll(checked: boolean) {
  const next = new Set(selectedIds.value);
  if (checked) {
    tables.value.forEach((t) => next.add(t.id));
  } else {
    tables.value.forEach((t) => next.delete(t.id));
  }
  selectedIds.value = next;
}

function clearSelection() {
  selectedIds.value = new Set();
  bulkTargetDb.value = null;
}

const importInputRef = ref<HTMLInputElement | null>(null);
const exporting = ref(false);
const importOpen = ref(false);
const importDragOver = ref(false);
const importing = ref(false);
const importError = ref<string | null>(null);

const metaOpen = ref(false);
const metaLoading = ref(false);
const metaSaving = ref(false);
const meta = ref<BDDMeta | null>(null);
const metaDraft = ref<{ description: string; usage: string }>({
  description: '',
  usage: '',
});

function formatDateTime(d?: string): string {
  if (!d) return '—';
  try {
    return new Date(d).toLocaleString('fr-FR');
  } catch {
    return d;
  }
}

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

async function openMetaModal() {
  metaOpen.value = true;
  metaLoading.value = true;
  try {
    const m = await bddApi.getMeta();
    meta.value = m;
    metaDraft.value = {
      description: m.description || '',
      usage: m.usage || '',
    };
  } catch (err) {
    if (err instanceof ApiError && err.status === 503) {
      toast.error('Service BDD indisponible');
    } else {
      toast.error('Impossible de charger les metadonnees');
    }
    metaOpen.value = false;
  } finally {
    metaLoading.value = false;
  }
}

function closeMetaModal() {
  if (metaSaving.value) return;
  metaOpen.value = false;
}

async function saveMeta() {
  if (metaSaving.value) return;
  metaSaving.value = true;
  try {
    const updated = await bddApi.putMeta({
      description: metaDraft.value.description,
      usage: metaDraft.value.usage,
    });
    meta.value = updated;
    toast.success('Metadonnees enregistrees');
    metaOpen.value = false;
  } catch (err) {
    const body = (err as { body?: { error?: string } })?.body;
    const msg =
      body?.error || (err instanceof Error ? err.message : 'Erreur inconnue');
    toast.error('Echec de l\'enregistrement: ' + msg);
  } finally {
    metaSaving.value = false;
  }
}

async function exportRegistry() {
  if (exporting.value) return;
  exporting.value = true;
  try {
    const blob = await bddApi.exportRegistry();
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download =
      'bdd-tables-export-' + new Date().toISOString().slice(0, 10) + '.json';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
    toast.success('Export genere');
  } catch (err) {
    if (err instanceof ApiError && err.status === 503) {
      toast.error('Service BDD indisponible');
    } else {
      toast.error('Echec de l\'export');
    }
  } finally {
    exporting.value = false;
  }
}

function openImportModal() {
  importOpen.value = true;
  importError.value = null;
  importDragOver.value = false;
}

function closeImportModal() {
  if (importing.value) return;
  importOpen.value = false;
  importError.value = null;
  importDragOver.value = false;
}

function onImportPicked(event: Event) {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0] ?? null;
  input.value = '';
  if (file) handleImportFile(file);
}

function onImportDrop(event: DragEvent) {
  importDragOver.value = false;
  const file = event.dataTransfer?.files?.[0] ?? null;
  if (file) handleImportFile(file);
}

function isExportShape(payload: unknown): boolean {
  if (!payload || typeof payload !== 'object') return false;
  const obj = payload as Record<string, unknown>;
  return Array.isArray(obj.tables);
}

function isDocShape(payload: unknown): boolean {
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
    return false;
  }
  const obj = payload as Record<string, unknown>;
  if (Object.prototype.hasOwnProperty.call(obj, '_meta')) return true;
  // Heuristic: at least one non-meta key looks like a doc-table entry.
  return Object.entries(obj).some(([k, v]) => {
    if (k.startsWith('_')) return false;
    if (!v || typeof v !== 'object') return false;
    const t = v as Record<string, unknown>;
    return 'columns' in t || 'description' in t;
  });
}

async function handleImportFile(file: File) {
  importError.value = null;

  if (
    !file.name.toLowerCase().endsWith('.json') &&
    file.type &&
    !file.type.includes('json')
  ) {
    importError.value = 'Type de fichier non supporte (JSON requis).';
    return;
  }

  importing.value = true;
  let payload: unknown;
  try {
    const text = await file.text();
    payload = JSON.parse(text);
  } catch {
    importError.value = 'Fichier JSON invalide.';
    importing.value = false;
    return;
  }

  try {
    let res: { inserted: number; updated: number; errors?: { error: string }[] };
    if (isExportShape(payload)) {
      res = await bddApi.importRegistry(payload);
    } else if (isDocShape(payload)) {
      res = await bddApi.importDoc(payload);
    } else {
      importError.value =
        'Format JSON non reconnu (attendu : export `{tables:[...]}` ou doc `{_meta, table_name:{...}}`).';
      importing.value = false;
      return;
    }

    const errCount = res.errors?.length ?? 0;
    const okMsg =
      res.inserted + ' insere(s), ' + res.updated + ' mis a jour';
    if (errCount === 0) {
      toast.success(okMsg);
    } else {
      toast.error(okMsg + ', ' + errCount + ' erreur(s)');
    }
    await Promise.all([loadCounts(), loadTables()]);
    importOpen.value = false;
  } catch (err) {
    const body = (err as { body?: { error?: string } })?.body;
    const msg =
      body?.error || (err instanceof Error ? err.message : 'Erreur inconnue');
    importError.value = 'Echec de l\'import: ' + msg;
  } finally {
    importing.value = false;
  }
}

async function applyBulkMove() {
  if (bulkTargetDb.value === null || selectedIds.value.size === 0 || bulkBusy.value) return;
  bulkBusy.value = true;
  try {
    const res = await bddApi.bulkUpdate({
      ids: Array.from(selectedIds.value),
      database_id: bulkTargetDb.value,
    });
    toast.success(res.affected + ' table(s) deplacee(s)');
    clearSelection();
    await Promise.all([loadCounts(), loadTables()]);
  } catch (err) {
    const body = (err as { body?: { error?: string } })?.body;
    const msg =
      body?.error || (err instanceof Error ? err.message : 'Erreur inconnue');
    toast.error('Echec du deplacement: ' + msg);
  } finally {
    bulkBusy.value = false;
  }
}

async function applyBulkActive(active: boolean) {
  if (selectedIds.value.size === 0 || bulkBusy.value) return;
  bulkBusy.value = true;
  try {
    const res = await bddApi.bulkUpdate({
      ids: Array.from(selectedIds.value),
      is_active: active,
    });
    toast.success(
      res.affected + ' table(s) ' + (active ? 'activee(s)' : 'desactivee(s)'),
    );
    clearSelection();
    await loadTables();
  } catch (err) {
    const body = (err as { body?: { error?: string } })?.body;
    const msg =
      body?.error || (err instanceof Error ? err.message : 'Erreur inconnue');
    toast.error('Echec de la mise a jour: ' + msg);
  } finally {
    bulkBusy.value = false;
  }
}

async function applyBulkDelete() {
  if (selectedIds.value.size === 0 || bulkBusy.value) return;
  bulkBusy.value = true;
  try {
    const res = await bddApi.bulkDelete({ ids: Array.from(selectedIds.value) });
    toast.success(res.affected + ' table(s) supprimee(s)');
    clearSelection();
    bulkDeleteOpen.value = false;
    await Promise.all([loadCounts(), loadTables()]);
  } catch (err) {
    const body = (err as { body?: { error?: string } })?.body;
    const msg =
      body?.error || (err instanceof Error ? err.message : 'Erreur inconnue');
    toast.error('Echec de la suppression: ' + msg);
  } finally {
    bulkBusy.value = false;
  }
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
