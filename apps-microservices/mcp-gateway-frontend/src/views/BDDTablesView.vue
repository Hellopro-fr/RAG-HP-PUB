<template>
  <div>
    <PageBreadcrumb page-title="Tables BDD Hellopro" />

    <div v-if="loading" class="text-center py-12">
      <i class="pi pi-spinner pi-spin text-2xl text-brand-500" />
    </div>

    <PageHeaderTabs
      v-else
      v-model="activeTab"
      :tabs="tabs"
    >
      <template #actions>
        <button
          v-if="authStore.isAdmin"
          class="px-4 py-2 text-sm font-medium text-white bg-brand-500 rounded-md hover:bg-brand-600"
          @click="showAddDialog = true"
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

      <!-- Empty state -->
      <div v-if="!filteredTables.length" class="text-center py-12 text-gray-500 dark:text-gray-400">
        <i class="pi pi-database text-4xl mb-3 block" />
        <p>Aucune table selectionnee pour cette base. Cliquez sur "Ajouter une table" pour commencer.</p>
      </div>

      <!-- Table -->
      <div v-else class="overflow-x-auto">
        <table class="min-w-full text-sm">
          <thead class="sticky top-0 bg-gray-50 dark:bg-gray-800/60">
            <tr class="text-left text-xs font-semibold uppercase text-gray-500 dark:text-gray-400">
              <th class="px-3 py-2">Nom de la table</th>
              <th class="px-3 py-2">Champs (utilises)</th>
              <th class="px-3 py-2">Description</th>
              <th class="px-3 py-2">Ajoutee le</th>
              <th class="px-3 py-2 text-right">Actions</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-100 dark:divide-gray-800">
            <template v-for="table in filteredTables" :key="table.id">
              <tr class="hover:bg-gray-50 dark:hover:bg-white/5">
                <td class="px-3 py-2">
                  <button
                    type="button"
                    class="inline-flex items-center gap-2 text-left text-gray-900 dark:text-white font-medium"
                    @click="toggleExpand(table)"
                  >
                    <i
                      class="pi text-xs text-gray-400 transition-transform"
                      :class="expanded[table.id] ? 'pi-chevron-down' : 'pi-chevron-right'"
                    />
                    <span class="font-mono">{{ table.table_name }}</span>
                  </button>
                </td>
                <td class="px-3 py-2 text-gray-600 dark:text-gray-300">
                  {{ table.fields.length }}
                  <span v-if="catalogCounts[table.id] !== undefined" class="text-gray-400 dark:text-gray-500">
                    / catalogue {{ catalogCounts[table.id] }}
                  </span>
                </td>
                <td class="px-3 py-2 text-gray-700 dark:text-gray-300 max-w-sm">
                  <textarea
                    v-if="editingDescriptionId === table.id"
                    v-model="descriptionDraft"
                    rows="2"
                    class="w-full rounded-md border border-gray-300 bg-transparent px-2 py-1 text-sm text-gray-800 dark:border-gray-700 dark:bg-gray-900 dark:text-white/90"
                    autofocus
                    @blur="saveDescription(table)"
                    @keydown.enter.prevent="saveDescription(table)"
                  />
                  <button
                    v-else-if="authStore.isAdmin"
                    type="button"
                    class="text-left w-full hover:underline text-gray-700 dark:text-gray-300"
                    @click="startEditDescription(table)"
                  >
                    <span v-if="table.description">{{ table.description }}</span>
                    <span v-else class="text-gray-400 italic">Cliquer pour ajouter</span>
                  </button>
                  <span v-else>{{ table.description || '—' }}</span>
                </td>
                <td class="px-3 py-2 text-gray-500 dark:text-gray-400 whitespace-nowrap">
                  {{ formatDate(table.created_at) }}
                </td>
                <td class="px-3 py-2 text-right">
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
              <!-- Expanded sub-pane -->
              <tr v-if="expanded[table.id]" class="bg-gray-50 dark:bg-gray-800/30">
                <td colspan="5" class="px-6 py-4">
                  <div v-if="loadingFields[table.id]" class="text-center py-4">
                    <i class="pi pi-spinner pi-spin text-lg text-brand-500" />
                  </div>
                  <div v-else>
                    <div
                      v-if="fieldsUnavailable[table.id]"
                      class="bg-warning-50 dark:bg-warning-500/15 border border-warning-200 dark:border-warning-500/30 rounded-md p-2 text-xs text-warning-700 dark:text-warning-400 mb-2"
                      title="Catalogue indisponible"
                    >
                      <i class="pi pi-exclamation-triangle mr-1" />
                      Catalogue indisponible
                    </div>
                    <table class="min-w-full text-xs">
                      <thead>
                        <tr class="text-left text-[11px] uppercase text-gray-500 dark:text-gray-400">
                          <th class="px-2 py-1">Nom</th>
                          <th class="px-2 py-1">Type</th>
                          <th class="px-2 py-1">Nullable</th>
                          <th class="px-2 py-1">Description (curee)</th>
                          <th class="px-2 py-1 text-right">Actions</th>
                        </tr>
                      </thead>
                      <tbody class="divide-y divide-gray-100 dark:divide-gray-800">
                        <tr v-for="field in table.fields" :key="field.id">
                          <td class="px-2 py-1 font-mono text-gray-900 dark:text-white">{{ field.field_name }}</td>
                          <td class="px-2 py-1 text-gray-600 dark:text-gray-300 font-mono">
                            {{ catalogFieldType(table.id, field.field_name) }}
                          </td>
                          <td class="px-2 py-1 text-gray-600 dark:text-gray-300">
                            {{ catalogFieldNullable(table.id, field.field_name) }}
                          </td>
                          <td class="px-2 py-1 max-w-sm">
                            <textarea
                              v-if="editingFieldId === field.id"
                              v-model="fieldDescriptionDraft"
                              rows="2"
                              class="w-full rounded-md border border-gray-300 bg-transparent px-2 py-1 text-xs text-gray-800 dark:border-gray-700 dark:bg-gray-900 dark:text-white/90"
                              autofocus
                              @blur="saveFieldDescription(table, field)"
                              @keydown.enter.prevent="saveFieldDescription(table, field)"
                            />
                            <button
                              v-else-if="authStore.isAdmin"
                              type="button"
                              class="text-left w-full hover:underline text-gray-700 dark:text-gray-300"
                              @click="startEditFieldDescription(field)"
                            >
                              <span v-if="field.description">{{ field.description }}</span>
                              <span v-else class="text-gray-400 italic">Cliquer pour ajouter</span>
                            </button>
                            <span v-else>{{ field.description || '—' }}</span>
                          </td>
                          <td class="px-2 py-1 text-right">
                            <button
                              v-if="authStore.isAdmin"
                              type="button"
                              class="p-1 rounded text-error-600 dark:text-error-400 hover:bg-error-50 dark:hover:bg-error-500/10"
                              title="Supprimer"
                              @click="deletingField = { table, field }"
                            >
                              <i class="pi pi-trash text-xs" />
                            </button>
                          </td>
                        </tr>
                        <tr v-if="!table.fields.length">
                          <td colspan="5" class="px-2 py-3 text-center text-gray-400 dark:text-gray-500 italic">
                            Aucun champ enregistre.
                          </td>
                        </tr>
                      </tbody>
                    </table>
                    <div v-if="authStore.isAdmin" class="mt-3 flex items-center gap-3 flex-wrap">
                      <button
                        v-if="!addFieldOpen[table.id]"
                        type="button"
                        class="text-xs px-3 py-1.5 rounded-md border border-brand-300 text-brand-500 hover:bg-brand-50 dark:hover:bg-brand-500/10"
                        @click="openAddField(table)"
                      >
                        + Ajouter un champ
                      </button>
                      <div
                        v-else
                        class="flex items-center gap-2 flex-wrap w-full"
                      >
                        <select
                          v-model="newFieldId[table.id]"
                          class="text-xs h-8 rounded-md border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-900 px-2"
                        >
                          <option :value="undefined">Choisir un champ</option>
                          <option
                            v-for="cf in availableCatalogFields(table)"
                            :key="cf.id"
                            :value="cf.id"
                          >
                            {{ cf.field_name }}{{ cf.field_type ? ' (' + cf.field_type + ')' : '' }}
                          </option>
                        </select>
                        <input
                          v-model="newFieldDescription[table.id]"
                          type="text"
                          placeholder="Description curee (optionnelle)"
                          class="text-xs h-8 flex-1 min-w-[200px] rounded-md border border-gray-300 dark:border-gray-700 bg-white dark:bg-gray-900 px-2"
                        />
                        <button
                          type="button"
                          class="text-xs px-3 py-1.5 rounded-md bg-brand-500 text-white hover:bg-brand-600 disabled:opacity-50"
                          :disabled="!newFieldId[table.id]"
                          @click="confirmAddField(table)"
                        >
                          Ajouter
                        </button>
                        <button
                          type="button"
                          class="text-xs px-3 py-1.5 rounded-md bg-gray-100 dark:bg-white/5 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700"
                          @click="cancelAddField(table)"
                        >
                          Annuler
                        </button>
                      </div>
                    </div>
                  </div>
                </td>
              </tr>
            </template>
          </tbody>
        </table>
      </div>
    </PageHeaderTabs>

    <!-- Add table dialog -->
    <BDDAddTableDialog
      :open="showAddDialog"
      :default-database-id="activeDb"
      :existing-tables="currentTables"
      @update:open="showAddDialog = $event"
      @created="handleCreated"
    />

    <!-- Delete table confirm -->
    <ConfirmDialog
      :open="!!deletingTable"
      title="Supprimer la table"
      message="Cette action est irreversible. La table et ses champs seront retires du registre."
      confirm-label="Supprimer"
      @update:open="deletingTable = undefined"
      @confirm="confirmDeleteTable"
    />

    <!-- Delete field confirm -->
    <ConfirmDialog
      :open="!!deletingField"
      title="Supprimer le champ"
      message="Le champ ne sera plus expose. Cette action est irreversible."
      confirm-label="Supprimer"
      @update:open="deletingField = undefined"
      @confirm="confirmDeleteField"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { bddApi } from '@/api/bdd';
import { HELLOPRO_DATABASES } from '@/types/bdd';
import type { BDDUsedTable, BDDUsedField, BDDCatalogField } from '@/types/bdd';
import { useAuthStore } from '@/stores/auth';
import { useToast } from '@/composables/useToast';
import { ApiError } from '@/types/api';
import PageBreadcrumb from '@/components/common/PageBreadcrumb.vue';
import PageHeaderTabs from '@/components/common/PageHeaderTabs.vue';
import ConfirmDialog from '@/components/shared/ConfirmDialog.vue';
import BDDAddTableDialog from '@/components/bdd/BDDAddTableDialog.vue';

const route = useRoute();
const router = useRouter();
const authStore = useAuthStore();
const toast = useToast();

const databases = HELLOPRO_DATABASES;

const loading = ref(true);
const search = ref('');
const showAddDialog = ref(false);

// Tables loaded for all 3 databases on mount.
// Tab-switch is local — no extra API call.
const tablesByDb = reactive<Record<number, BDDUsedTable[]>>({});

// activeTab uses the database slug (string) so it plays nice with PageHeaderTabs.
const activeTab = ref<string>(parseInitialTab());
const activeDb = computed<number>(() => {
  const found = databases.find((d) => d.slug === activeTab.value);
  return found ? found.id : databases[0].id;
});
const currentTables = computed<BDDUsedTable[]>(() => tablesByDb[activeDb.value] || []);

const tabs = computed(() =>
  databases.map((d) => ({
    label: d.name,
    value: d.slug,
    count: (tablesByDb[d.id] || []).length,
  })),
);

const expanded = reactive<Record<string, boolean>>({});
const loadingFields = reactive<Record<string, boolean>>({});
const fieldsUnavailable = reactive<Record<string, boolean>>({});
const catalogCounts = reactive<Record<string, number>>({});
const catalogFieldsByTable = reactive<Record<string, BDDCatalogField[]>>({});

const editingDescriptionId = ref<string>();
const descriptionDraft = ref('');

const editingFieldId = ref<string>();
const fieldDescriptionDraft = ref('');

const addFieldOpen = reactive<Record<string, boolean>>({});
const newFieldId = reactive<Record<string, number | undefined>>({});
const newFieldDescription = reactive<Record<string, string>>({});

const deletingTable = ref<BDDUsedTable | undefined>();
const deletingField = ref<{ table: BDDUsedTable; field: BDDUsedField } | undefined>();

function parseInitialTab(): string {
  const raw = String(route.query.db || '');
  const byId = databases.find((d) => String(d.id) === raw);
  if (byId) return byId.slug;
  const bySlug = databases.find((d) => d.slug === raw);
  if (bySlug) return bySlug.slug;
  return databases[0].slug;
}

const filteredTables = computed(() => {
  const q = search.value.trim().toLowerCase();
  const list = currentTables.value;
  if (!q) return list;
  return list.filter((t) =>
    t.table_name.toLowerCase().includes(q) ||
    (t.description || '').toLowerCase().includes(q),
  );
});

onMounted(loadAllTables);

watch(activeTab, () => {
  // Sync route query so refresh keeps the tab; collapse expanded rows.
  router.replace({ query: { ...route.query, db: String(activeDb.value) } });
  Object.keys(expanded).forEach((k) => delete expanded[k]);
});

async function loadAllTables() {
  loading.value = true;
  let serviceUnavailable = false;
  try {
    const results = await Promise.all(
      databases.map(async (d) => {
        try {
          const res = await bddApi.listUsed(d.id);
          return { dbId: d.id, tables: res.tables || [] };
        } catch (err) {
          if (err instanceof ApiError && err.status === 503) serviceUnavailable = true;
          return { dbId: d.id, tables: [] as BDDUsedTable[] };
        }
      }),
    );
    for (const r of results) tablesByDb[r.dbId] = r.tables;
    if (serviceUnavailable) toast.error('Service BDD indisponible');
  } catch {
    toast.error('Impossible de charger les tables');
  } finally {
    loading.value = false;
  }
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

async function toggleExpand(table: BDDUsedTable) {
  if (expanded[table.id]) {
    expanded[table.id] = false;
    return;
  }
  expanded[table.id] = true;
  if (!catalogFieldsByTable[table.id] && !fieldsUnavailable[table.id]) {
    await loadCatalogForTable(table);
  }
}

async function loadCatalogForTable(table: BDDUsedTable) {
  if (!table.upstream_table_id) {
    fieldsUnavailable[table.id] = true;
    return;
  }
  loadingFields[table.id] = true;
  try {
    const res = await bddApi.catalogFields(table.database_id, table.upstream_table_id);
    catalogFieldsByTable[table.id] = res.fields || [];
    catalogCounts[table.id] = (res.fields || []).length;
  } catch {
    fieldsUnavailable[table.id] = true;
  } finally {
    loadingFields[table.id] = false;
  }
}

function catalogFieldType(tableId: string, fieldName: string): string {
  const list = catalogFieldsByTable[tableId];
  if (!list) return '—';
  const f = list.find((x) => x.field_name === fieldName);
  return f?.field_type || '—';
}

function catalogFieldNullable(tableId: string, fieldName: string): string {
  const list = catalogFieldsByTable[tableId];
  if (!list) return '—';
  const f = list.find((x) => x.field_name === fieldName);
  if (!f) return '—';
  if (f.is_nullable === undefined) return '—';
  return f.is_nullable ? 'oui' : 'non';
}

function startEditDescription(table: BDDUsedTable) {
  if (!authStore.isAdmin) return;
  editingDescriptionId.value = table.id;
  descriptionDraft.value = table.description || '';
}

async function saveDescription(table: BDDUsedTable) {
  if (editingDescriptionId.value !== table.id) return;
  const next = descriptionDraft.value.trim();
  editingDescriptionId.value = undefined;
  if (next === (table.description || '')) return;
  try {
    const updated = await bddApi.patchUsed(table.id, { description: next });
    table.description = updated.description;
    toast.success('Description mise a jour');
  } catch {
    toast.error('Impossible de mettre a jour la description');
  }
}

function startEditFieldDescription(field: BDDUsedField) {
  if (!authStore.isAdmin) return;
  editingFieldId.value = field.id;
  fieldDescriptionDraft.value = field.description || '';
}

async function saveFieldDescription(table: BDDUsedTable, field: BDDUsedField) {
  if (editingFieldId.value !== field.id) return;
  const next = fieldDescriptionDraft.value.trim();
  editingFieldId.value = undefined;
  if (next === (field.description || '')) return;
  try {
    const updated = await bddApi.patchField(table.id, field.id, { description: next });
    field.description = updated.description;
    toast.success('Description mise a jour');
  } catch {
    toast.error('Impossible de mettre a jour la description');
  }
}

async function confirmDeleteTable() {
  if (!deletingTable.value) return;
  const target = deletingTable.value;
  try {
    await bddApi.deleteUsed(target.id);
    tablesByDb[target.database_id] = (tablesByDb[target.database_id] || []).filter(
      (t) => t.id !== target.id,
    );
    toast.success('Table supprimee');
  } catch {
    toast.error('Impossible de supprimer la table');
  } finally {
    deletingTable.value = undefined;
  }
}

async function confirmDeleteField() {
  if (!deletingField.value) return;
  const { table, field } = deletingField.value;
  try {
    await bddApi.deleteField(table.id, field.id);
    table.fields = table.fields.filter((f) => f.id !== field.id);
    toast.success('Champ supprime');
  } catch {
    toast.error('Impossible de supprimer le champ');
  } finally {
    deletingField.value = undefined;
  }
}

function availableCatalogFields(table: BDDUsedTable): BDDCatalogField[] {
  const list = catalogFieldsByTable[table.id] || [];
  const usedNames = new Set(table.fields.map((f) => f.field_name));
  return list.filter((cf) => !usedNames.has(cf.field_name));
}

function openAddField(table: BDDUsedTable) {
  addFieldOpen[table.id] = true;
  newFieldDescription[table.id] = '';
  newFieldId[table.id] = undefined;
}

function cancelAddField(table: BDDUsedTable) {
  addFieldOpen[table.id] = false;
  newFieldDescription[table.id] = '';
  newFieldId[table.id] = undefined;
}

async function confirmAddField(table: BDDUsedTable) {
  const fid = newFieldId[table.id];
  if (!fid) return;
  const cf = (catalogFieldsByTable[table.id] || []).find((x) => x.id === fid);
  if (!cf) return;
  try {
    const created = await bddApi.addField(table.id, {
      field_name: cf.field_name,
      description: (newFieldDescription[table.id] || '').trim() || undefined,
      upstream_field_id: cf.id,
    });
    table.fields = [...table.fields, created];
    cancelAddField(table);
    toast.success('Champ ajoute');
  } catch {
    toast.error('Impossible d ajouter le champ');
  }
}

function handleCreated(created: BDDUsedTable) {
  showAddDialog.value = false;
  const list = tablesByDb[created.database_id] || [];
  tablesByDb[created.database_id] = [created, ...list];
  // Switch to the tab that holds the newly created row if needed.
  if (created.database_id !== activeDb.value) {
    const target = databases.find((d) => d.id === created.database_id);
    if (target) activeTab.value = target.slug;
  }
}
</script>
