<template>
  <div>
    <PageBreadcrumb page-title="Ajouter une table BDD" />

    <div
      class="rounded-2xl border border-gray-200 bg-white dark:border-gray-800 dark:bg-white/[0.03]"
    >
      <!-- Stepper indicator -->
      <div class="flex items-center justify-between border-b border-gray-100 px-6 py-4 dark:border-gray-800">
        <div class="flex items-center gap-3">
          <template v-for="(label, idx) in stepLabels" :key="idx">
            <div
              class="flex items-center gap-2"
              :class="
                step === idx + 1
                  ? 'text-blue-600 dark:text-blue-400'
                  : step > idx + 1
                    ? 'text-gray-700 dark:text-gray-300'
                    : 'text-gray-400 dark:text-gray-500'
              "
            >
              <span
                class="inline-flex h-6 w-6 items-center justify-center rounded-full border text-xs font-semibold"
                :class="
                  step === idx + 1
                    ? 'border-blue-500 bg-blue-50 text-blue-600 dark:border-blue-400 dark:bg-blue-500/10 dark:text-blue-400'
                    : step > idx + 1
                      ? 'border-gray-300 bg-gray-50 text-gray-700 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-300'
                      : 'border-gray-200 text-gray-400 dark:border-gray-700 dark:text-gray-500'
                "
              >
                <i v-if="step > idx + 1" class="pi pi-check text-[10px]" />
                <span v-else>{{ idx + 1 }}</span>
              </span>
              <span class="text-sm font-medium">{{ label }}</span>
            </div>
            <span
              v-if="idx < stepLabels.length - 1"
              class="h-px w-8 bg-gray-200 dark:bg-gray-700"
            />
          </template>
        </div>
      </div>

      <!-- Body -->
      <div class="p-6">
        <!-- Step 1: choose the database -->
        <div v-if="step === 1">
          <p class="mb-4 text-sm text-gray-600 dark:text-gray-400">
            Choisissez la base Hellopro dans laquelle ajouter une nouvelle table.
          </p>
          <div class="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <button
              v-for="db in HELLOPRO_DATABASES"
              :key="db.id"
              type="button"
              class="flex flex-col items-center gap-3 rounded-xl border p-6 text-center transition-colors"
              :class="
                selectedDatabaseId === db.id
                  ? 'border-brand-500 bg-brand-50 ring-2 ring-brand-500/30 dark:bg-brand-500/10'
                  : 'border-gray-200 hover:border-gray-300 dark:border-gray-700 dark:hover:border-gray-600'
              "
              @click="selectedDatabaseId = db.id"
            >
              <i
                class="pi pi-database text-3xl"
                :class="
                  selectedDatabaseId === db.id
                    ? 'text-brand-500'
                    : 'text-gray-400 dark:text-gray-500'
                "
              />
              <div>
                <div class="text-base font-semibold text-gray-900 dark:text-white">
                  {{ db.name }}
                </div>
                <div class="mt-1 text-xs text-gray-500 dark:text-gray-400">
                  ID {{ db.id }}
                </div>
              </div>
            </button>
          </div>
        </div>

        <!-- Step 2: choose tables -->
        <div v-else-if="step === 2">
          <!-- 503 banner -->
          <div
            v-if="catalogUnavailable"
            class="mb-4 rounded-lg border border-warning-300 bg-warning-50 p-4 text-sm text-warning-800 dark:border-warning-500/30 dark:bg-warning-500/15 dark:text-warning-400"
          >
            <i class="pi pi-exclamation-triangle mr-2" />
            L'integration BDD n'est pas configuree (BDD_CATALOG_BASE_URL / BDD_CATALOG_TOKEN manquants)
          </div>

          <!-- Search -->
          <div class="mb-3">
            <input
              v-model="search"
              type="search"
              placeholder="Rechercher dans le catalogue Hellopro BDD"
              class="h-10 w-full rounded-lg border border-gray-300 bg-transparent px-4 py-2 text-sm text-gray-800 placeholder:text-gray-400 focus:border-brand-300 focus:outline-hidden focus:ring-3 focus:ring-brand-500/10 dark:border-gray-700 dark:bg-gray-900 dark:text-white/90"
            />
          </div>

          <!-- Selection counter -->
          <div class="mb-2 flex items-center justify-between">
            <span class="text-sm text-gray-600 dark:text-gray-400">
              {{ selectedTables.length }} table(s) selectionnee(s)
            </span>
            <span class="text-xs text-gray-400 dark:text-gray-500">
              Maximum 50 tables par ajout
            </span>
          </div>

          <!-- Loading -->
          <div v-if="catalogLoading" class="flex items-center justify-center py-12">
            <i class="pi pi-spinner pi-spin text-2xl text-brand-500" />
          </div>

          <!-- Empty / unavailable -->
          <div
            v-else-if="catalogUnavailable"
            class="rounded-lg border border-dashed border-gray-200 px-4 py-12 text-center text-sm text-gray-500 dark:border-gray-700 dark:text-gray-400"
          >
            Catalogue indisponible
          </div>
          <div
            v-else-if="catalogTables.length === 0"
            class="rounded-lg border border-dashed border-gray-200 px-4 py-12 text-center text-sm text-gray-500 dark:border-gray-700 dark:text-gray-400"
          >
            Aucun resultat
          </div>

          <!-- Table list -->
          <div
            v-else
            class="overflow-x-auto rounded-lg border border-gray-200 dark:border-gray-700"
          >
            <table class="min-w-full text-sm">
              <thead class="bg-gray-50 dark:bg-gray-800/60">
                <tr class="text-left text-xs font-semibold uppercase text-gray-500 dark:text-gray-400">
                  <th class="w-10 px-3 py-2"></th>
                  <th class="px-3 py-2">Nom de la table</th>
                  <th class="px-3 py-2">Champs</th>
                  <th class="px-3 py-2">Description</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-gray-100 dark:divide-gray-800">
                <tr
                  v-for="row in catalogTables"
                  :key="row.id"
                  class="transition-colors"
                  :class="
                    isRegistered(row)
                      ? 'cursor-not-allowed opacity-60'
                      : 'cursor-pointer hover:bg-gray-50 dark:hover:bg-white/5'
                  "
                  @click="!isRegistered(row) && toggleRow(row)"
                >
                  <td class="px-3 py-2">
                    <input
                      type="checkbox"
                      class="rounded border-gray-300 text-brand-500 dark:border-gray-700"
                      :checked="isSelected(row)"
                      :disabled="isRegistered(row)"
                      @click.stop="!isRegistered(row) && toggleRow(row)"
                    />
                  </td>
                  <td class="px-3 py-2 font-mono text-gray-900 dark:text-white">
                    {{ row.table_name }}
                    <span
                      v-if="isRegistered(row)"
                      class="ml-2 inline-flex items-center rounded-full bg-gray-100 px-2 py-0.5 text-[10px] font-medium text-gray-600 dark:bg-gray-700 dark:text-gray-300"
                    >
                      Deja enregistree
                    </span>
                  </td>
                  <td class="px-3 py-2 text-gray-600 dark:text-gray-300">
                    {{ row.field_count ?? '—' }}
                  </td>
                  <td class="px-3 py-2 text-gray-700 dark:text-gray-300 max-w-sm truncate">
                    <span v-if="row.description">{{ row.description }}</span>
                    <span v-else class="text-gray-400">—</span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <!-- Step 3: recap -->
        <div v-else-if="step === 3">
          <div class="mb-4">
            <div class="text-sm font-medium text-gray-700 dark:text-gray-300">
              Base de donnees:
              <span class="font-semibold text-gray-900 dark:text-white">
                {{ selectedDatabaseName }}
              </span>
              <button
                type="button"
                class="ml-2 text-xs text-brand-500 hover:text-brand-600"
                @click="step = 1"
              >
                Modifier
              </button>
            </div>
          </div>

          <div class="mb-4">
            <div class="mb-2 text-sm font-medium text-gray-700 dark:text-gray-300">
              Tables a ajouter ({{ selectedTables.length }})
              <button
                type="button"
                class="ml-2 text-xs text-brand-500 hover:text-brand-600"
                @click="step = 2"
              >
                Modifier
              </button>
            </div>
            <ul class="space-y-1 rounded-lg border border-gray-200 p-3 dark:border-gray-700">
              <li
                v-for="t in selectedTables"
                :key="t.id"
                class="text-sm text-gray-800 dark:text-gray-200"
              >
                <span class="font-mono">{{ t.table_name }}</span>
                <span class="text-gray-400 dark:text-gray-500">
                  — {{ t.field_count ?? 0 }} champs disponibles
                </span>
              </li>
            </ul>
          </div>

          <div
            class="rounded-lg border border-blue-200 bg-blue-50 p-4 text-sm text-blue-800 dark:border-blue-500/30 dark:bg-blue-500/15 dark:text-blue-300"
          >
            <i class="pi pi-info-circle mr-2" />
            Les tables ajoutees seront marquees inactives. Configurez ensuite leurs champs pour les activer.
          </div>
        </div>
      </div>

      <!-- Footer -->
      <div
        class="flex items-center justify-between gap-3 border-t border-gray-100 px-6 py-4 dark:border-gray-800"
      >
        <button
          type="button"
          class="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-200 border border-gray-300 dark:border-gray-600 rounded-md hover:bg-gray-50 dark:hover:bg-gray-700"
          @click="router.push('/bdd-tables')"
        >
          Annuler
        </button>
        <div class="flex items-center gap-3">
          <button
            v-if="step > 1"
            type="button"
            class="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-200 border border-gray-300 dark:border-gray-600 rounded-md hover:bg-gray-50 dark:hover:bg-gray-700"
            @click="goBack"
          >
            Precedent
          </button>
          <button
            v-if="step < 3"
            type="button"
            class="px-4 py-2 text-sm font-medium text-white bg-brand-500 rounded-md hover:bg-brand-600 disabled:opacity-50 disabled:cursor-not-allowed"
            :disabled="!canGoNext"
            @click="goNext"
          >
            Suivant
          </button>
          <button
            v-else
            type="button"
            class="px-4 py-2 text-sm font-medium text-white bg-brand-500 rounded-md hover:bg-brand-600 disabled:opacity-50 disabled:cursor-not-allowed"
            :disabled="loading || selectedTables.length === 0"
            @click="submit"
          >
            <i v-if="loading" class="pi pi-spinner pi-spin mr-1" />
            Confirmer l'ajout
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue';
import { useRouter } from 'vue-router';
import { bddApi } from '@/api/bdd';
import { HELLOPRO_DATABASES } from '@/types/bdd';
import type { BDDCatalogTable } from '@/types/bdd';
import { useAuthStore } from '@/stores/auth';
import { useToast } from '@/composables/useToast';
import { ApiError } from '@/types/api';
import PageBreadcrumb from '@/components/common/PageBreadcrumb.vue';

const MAX_SELECTION = 50;
const SEARCH_DEBOUNCE_MS = 300;

const router = useRouter();
const authStore = useAuthStore();
const toast = useToast();

const stepLabels = ['Choisir la base', 'Choisir les tables', 'Recapitulatif'];

const step = ref<1 | 2 | 3>(1);
const selectedDatabaseId = ref<number | null>(null);
const selectedTables = ref<BDDCatalogTable[]>([]);
const catalogTables = ref<BDDCatalogTable[]>([]);
const registeredNames = ref<Set<string>>(new Set());
const search = ref('');
const debouncedSearch = ref('');
const catalogLoading = ref(false);
const catalogUnavailable = ref(false);
const loading = ref(false);

let searchTimer: ReturnType<typeof setTimeout> | undefined;

const selectedDatabaseName = computed(() => {
  return (
    HELLOPRO_DATABASES.find((d) => d.id === selectedDatabaseId.value)?.name || '—'
  );
});

const canGoNext = computed(() => {
  if (step.value === 1) {
    return selectedDatabaseId.value !== null;
  }
  if (step.value === 2) {
    return selectedTables.value.length >= 1 && !catalogUnavailable.value;
  }
  return false;
});

function isSelected(row: BDDCatalogTable): boolean {
  return selectedTables.value.some((t) => t.id === row.id);
}

function isRegistered(row: BDDCatalogTable): boolean {
  return registeredNames.value.has(row.table_name);
}

function toggleRow(row: BDDCatalogTable) {
  if (isRegistered(row)) return;
  const idx = selectedTables.value.findIndex((t) => t.id === row.id);
  if (idx >= 0) {
    selectedTables.value.splice(idx, 1);
    return;
  }
  if (selectedTables.value.length >= MAX_SELECTION) {
    toast.error(`Maximum ${MAX_SELECTION} tables par ajout`);
    return;
  }
  selectedTables.value.push(row);
}

async function loadCatalog() {
  if (selectedDatabaseId.value === null) return;
  catalogLoading.value = true;
  catalogUnavailable.value = false;
  try {
    const res = await bddApi.catalogTables(
      selectedDatabaseId.value,
      debouncedSearch.value,
    );
    catalogTables.value = res.tables || [];
  } catch (err) {
    if (err instanceof ApiError && err.status === 503) {
      catalogUnavailable.value = true;
    } else {
      toast.error('Impossible de charger le catalogue');
    }
    catalogTables.value = [];
  } finally {
    catalogLoading.value = false;
  }
}

async function loadRegisteredNames() {
  if (selectedDatabaseId.value === null) return;
  try {
    const res = await bddApi.listUsed({
      database_id: selectedDatabaseId.value,
      limit: 100,
    });
    registeredNames.value = new Set((res.tables || []).map((t) => t.table_name));
  } catch (err) {
    if (err instanceof ApiError && err.status === 503) {
      catalogUnavailable.value = true;
    }
    registeredNames.value = new Set();
  }
}

function goNext() {
  if (!canGoNext.value) return;
  if (step.value === 1) {
    step.value = 2;
    return;
  }
  if (step.value === 2) {
    step.value = 3;
  }
}

function goBack() {
  if (step.value === 3) {
    step.value = 2;
    return;
  }
  if (step.value === 2) {
    step.value = 1;
  }
}

async function submit() {
  if (selectedDatabaseId.value === null || selectedTables.value.length === 0) return;
  loading.value = true;
  try {
    const res = await bddApi.bulkCreateUsed({
      database_id: selectedDatabaseId.value,
      items: selectedTables.value.map((t) => ({
        table_name: t.table_name,
        upstream_table_id: t.id,
      })),
    });
    if (res.errors && res.errors.length) {
      toast.error(
        `${res.errors.length} table(s) non ajoutee(s) (deja enregistree(s) ou invalide(s))`,
      );
    }
    if (res.created.length) {
      toast.success(
        `${res.created.length} table(s) ajoutee(s) - configurez les champs pour les activer`,
      );
      // Best-effort: pull primary key + row count from the upstream
      // catalog for each newly inserted table. Failures are silent (log
      // only) — the admin can still trigger a manual refresh from the
      // fields-edit page.
      await Promise.allSettled(
        res.created.map((t) => bddApi.refreshCatalog(t.id)),
      );
    }
    const slug = HELLOPRO_DATABASES.find(
      (d) => d.id === selectedDatabaseId.value,
    )?.slug;
    router.push({ path: '/bdd-tables', query: slug ? { db: slug } : {} });
  } catch (err) {
    toast.error("Echec de l'ajout en masse");
  } finally {
    loading.value = false;
  }
}

watch(search, (value) => {
  if (searchTimer) clearTimeout(searchTimer);
  searchTimer = setTimeout(() => {
    debouncedSearch.value = value.trim();
  }, SEARCH_DEBOUNCE_MS);
});

watch(debouncedSearch, () => {
  if (step.value === 2) loadCatalog();
});

watch(step, async (next, prev) => {
  if (next === 2 && prev !== 2) {
    await Promise.all([loadCatalog(), loadRegisteredNames()]);
  }
});

watch(selectedDatabaseId, () => {
  // If user changes the DB, reset step-2 state.
  selectedTables.value = [];
  catalogTables.value = [];
  registeredNames.value = new Set();
  search.value = '';
  debouncedSearch.value = '';
});

onMounted(() => {
  if (!authStore.isAdmin) {
    router.replace('/tokens');
  }
});
</script>
