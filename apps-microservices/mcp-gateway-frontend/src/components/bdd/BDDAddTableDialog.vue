<template>
  <DialogRoot :open="open" @update:open="handleOpenChange">
    <DialogPortal>
      <DialogOverlay class="fixed inset-0 bg-black/50 z-50" />
      <DialogContent
        class="fixed left-1/2 top-1/2 z-50 w-full max-w-2xl -translate-x-1/2 -translate-y-1/2 rounded-lg bg-white dark:bg-gray-900 p-6 shadow-theme-xl max-h-[90vh] overflow-y-auto"
      >
        <DialogTitle class="text-lg font-semibold text-gray-900 dark:text-white mb-1">
          Ajouter une table
        </DialogTitle>
        <DialogDescription class="text-sm text-gray-500 dark:text-gray-400 mb-4">
          {{ stepLabels[currentStep] }}
        </DialogDescription>

        <StepTabs
          :steps="stepLabels"
          :current-step="currentStep"
          :completed-steps="completedSteps"
          @update:current-step="goToStep"
        />

        <!-- Step 0: Choose database -->
        <div v-if="currentStep === 0" class="space-y-3">
          <p class="text-sm text-gray-700 dark:text-gray-300">
            Choisissez la base de donnees Hellopro a explorer.
          </p>
          <div class="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <button
              v-for="db in databases"
              :key="db.id"
              type="button"
              class="text-left rounded-lg border p-4 transition-colors"
              :class="form.databaseId === db.id
                ? 'border-brand-500 bg-brand-50/50 dark:bg-brand-500/10 dark:border-brand-400'
                : 'border-gray-200 dark:border-gray-700 hover:border-gray-400 dark:hover:border-gray-500 bg-white dark:bg-gray-900'"
              @click="selectDatabase(db.id)"
            >
              <div class="flex items-center justify-between">
                <span class="text-sm font-semibold text-gray-900 dark:text-white">{{ db.name }}</span>
                <i v-if="form.databaseId === db.id" class="pi pi-check-circle text-brand-500" />
              </div>
              <p class="text-xs text-gray-500 dark:text-gray-400 mt-1">id={{ db.id }}</p>
            </button>
          </div>
        </div>

        <!-- Step 1: Pick a catalog table -->
        <div v-else-if="currentStep === 1" class="space-y-3">
          <input
            v-model="catalogSearch"
            type="text"
            placeholder="Rechercher une table..."
            class="h-10 w-full rounded-lg border border-gray-300 bg-transparent px-4 py-2 text-sm text-gray-800 shadow-theme-xs placeholder:text-gray-400 focus:border-brand-300 focus:outline-hidden focus:ring-3 focus:ring-brand-500/10 dark:border-gray-700 dark:bg-gray-900 dark:text-white/90 dark:placeholder:text-white/30"
          />
          <div
            v-if="step1Error === 'duplicate'"
            class="bg-error-50 dark:bg-error-500/15 border border-error-200 dark:border-error-500/30 rounded-md p-3 text-sm text-error-600 dark:text-error-400"
          >
            <i class="pi pi-exclamation-triangle mr-1" />
            Cette table est deja enregistree pour cette base.
          </div>
          <div
            v-if="catalogUnavailable"
            class="bg-warning-50 dark:bg-warning-500/15 border border-warning-200 dark:border-warning-500/30 rounded-md p-3 text-sm text-warning-700 dark:text-warning-400 flex items-center justify-between gap-3"
          >
            <span>
              <i class="pi pi-exclamation-triangle mr-1" />
              Catalogue indisponible (503).
            </span>
            <button
              type="button"
              class="text-xs px-2 py-1 rounded-md border border-warning-300 dark:border-warning-500/50 hover:bg-warning-100 dark:hover:bg-warning-500/25"
              @click="loadCatalogTables"
            >
              Reessayer
            </button>
          </div>
          <div v-if="loadingCatalog" class="text-center py-6">
            <i class="pi pi-spinner pi-spin text-xl text-brand-500" />
          </div>
          <div
            v-else-if="catalogTables.length"
            class="max-h-72 overflow-y-auto border border-gray-200 dark:border-gray-700 rounded-lg divide-y divide-gray-100 dark:divide-gray-800"
          >
            <button
              v-for="t in catalogTables"
              :key="t.id"
              type="button"
              class="w-full text-left p-3 transition-colors"
              :class="[
                isAlreadyRegistered(t)
                  ? 'opacity-50 cursor-not-allowed bg-gray-50 dark:bg-gray-800/40'
                  : 'hover:bg-gray-50 dark:hover:bg-white/5',
                form.catalogTableId === t.id ? 'bg-brand-50 dark:bg-brand-500/10' : ''
              ]"
              :disabled="isAlreadyRegistered(t)"
              @click="selectCatalogTable(t)"
            >
              <div class="flex items-center justify-between gap-2">
                <span class="text-sm font-semibold text-gray-900 dark:text-white truncate">{{ t.table_name }}</span>
                <span v-if="t.field_count !== undefined" class="text-xs text-gray-500 dark:text-gray-400 shrink-0">
                  {{ t.field_count }} champ(s)
                </span>
              </div>
              <p
                v-if="t.description"
                class="text-xs text-gray-500 dark:text-gray-400 mt-1 line-clamp-2"
              >{{ t.description }}</p>
              <p
                v-if="isAlreadyRegistered(t)"
                class="text-xs text-warning-600 dark:text-warning-400 mt-1"
              >
                Deja enregistree
              </p>
            </button>
          </div>
          <div
            v-else-if="!loadingCatalog && !catalogUnavailable"
            class="text-center py-8 text-sm text-gray-500 dark:text-gray-400"
          >
            Aucune table trouvee.
          </div>
        </div>

        <!-- Step 2: Select fields -->
        <div v-else-if="currentStep === 2" class="space-y-3">
          <div class="flex items-center justify-between">
            <p class="text-sm text-gray-700 dark:text-gray-300">
              Selectionnez les champs a exposer.
            </p>
            <div class="flex gap-2">
              <button
                type="button"
                class="text-xs px-2 py-1 rounded-md border border-gray-300 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-white/5"
                @click="selectAllFields"
              >
                Tout selectionner
              </button>
              <button
                type="button"
                class="text-xs px-2 py-1 rounded-md border border-gray-300 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-white/5"
                @click="deselectAllFields"
              >
                Tout deselectionner
              </button>
            </div>
          </div>
          <div
            v-if="fieldsUnavailable"
            class="bg-warning-50 dark:bg-warning-500/15 border border-warning-200 dark:border-warning-500/30 rounded-md p-3 text-sm text-warning-700 dark:text-warning-400 flex items-center justify-between gap-3"
          >
            <span>
              <i class="pi pi-exclamation-triangle mr-1" />
              Catalogue indisponible (503).
            </span>
            <button
              type="button"
              class="text-xs px-2 py-1 rounded-md border border-warning-300 dark:border-warning-500/50 hover:bg-warning-100 dark:hover:bg-warning-500/25"
              @click="loadCatalogFields"
            >
              Reessayer
            </button>
          </div>
          <div v-if="loadingFields" class="text-center py-6">
            <i class="pi pi-spinner pi-spin text-xl text-brand-500" />
          </div>
          <div
            v-else-if="catalogFields.length"
            class="max-h-72 overflow-y-auto border border-gray-200 dark:border-gray-700 rounded-lg divide-y divide-gray-100 dark:divide-gray-800"
          >
            <div
              v-for="f in catalogFields"
              :key="f.id"
              class="p-3"
            >
              <label class="flex items-start gap-3 cursor-pointer">
                <input
                  type="checkbox"
                  class="mt-0.5 rounded border-gray-300 text-brand-500 dark:border-gray-700"
                  :checked="!!fieldSelections[f.id]"
                  @change="toggleField(f)"
                />
                <div class="flex-1 min-w-0">
                  <div class="flex items-center gap-2">
                    <span class="text-sm font-medium text-gray-900 dark:text-white truncate">{{ f.field_name }}</span>
                    <span v-if="f.field_type" class="text-xs text-gray-500 dark:text-gray-400 font-mono">
                      {{ f.field_type }}
                    </span>
                    <span v-if="f.is_nullable" class="text-[10px] text-gray-400 dark:text-gray-500">
                      nullable
                    </span>
                  </div>
                  <p
                    v-if="f.description"
                    class="text-xs text-gray-500 dark:text-gray-400 mt-0.5 line-clamp-2"
                  >{{ f.description }}</p>
                  <button
                    v-if="fieldSelections[f.id]"
                    type="button"
                    class="text-xs text-brand-500 hover:text-brand-600 mt-1"
                    @click.prevent="toggleFieldDescriptionEdit(f.id)"
                  >
                    {{ fieldDescriptionsOpen[f.id] ? 'Masquer la description curee' : 'Ajouter une description curee' }}
                  </button>
                  <textarea
                    v-if="fieldSelections[f.id] && fieldDescriptionsOpen[f.id]"
                    v-model="fieldCuratedDescriptions[f.id]"
                    rows="2"
                    placeholder="Description curee (optionnelle)"
                    class="mt-2 w-full rounded-md border border-gray-300 bg-transparent px-3 py-2 text-xs text-gray-800 shadow-theme-xs placeholder:text-gray-400 focus:border-brand-300 focus:outline-hidden focus:ring-3 focus:ring-brand-500/10 dark:border-gray-700 dark:bg-gray-900 dark:text-white/90 dark:placeholder:text-white/30"
                  />
                </div>
              </label>
            </div>
          </div>
          <p v-if="selectedFieldCount === 0" class="text-xs text-gray-500 dark:text-gray-400">
            Selectionnez au moins 1 champ pour continuer.
          </p>
          <p v-else class="text-xs text-gray-500 dark:text-gray-400">
            {{ selectedFieldCount }} champ(s) selectionne(s).
          </p>
        </div>

        <!-- Step 3: Table description -->
        <div v-else-if="currentStep === 3" class="space-y-3">
          <p class="text-sm text-gray-700 dark:text-gray-300">
            Description de la table (optionnel).
          </p>
          <textarea
            v-model="form.tableDescription"
            rows="4"
            placeholder="Description de la table"
            class="w-full rounded-lg border border-gray-300 bg-transparent px-4 py-2.5 text-sm text-gray-800 shadow-theme-xs placeholder:text-gray-400 focus:border-brand-300 focus:outline-hidden focus:ring-3 focus:ring-brand-500/10 dark:border-gray-700 dark:bg-gray-900 dark:text-white/90 dark:placeholder:text-white/30"
          />
        </div>

        <!-- Step 4: Recap -->
        <div v-else-if="currentStep === 4" class="space-y-4">
          <h3 class="text-sm font-semibold text-gray-900 dark:text-white">Recapitulatif</h3>
          <dl class="divide-y divide-gray-100 dark:divide-gray-800 text-sm">
            <div class="py-2 grid grid-cols-3 gap-4">
              <dt class="text-gray-500 dark:text-gray-400">Base</dt>
              <dd class="text-gray-900 dark:text-white col-span-2">{{ selectedDatabaseName }}</dd>
            </div>
            <div class="py-2 grid grid-cols-3 gap-4">
              <dt class="text-gray-500 dark:text-gray-400">Table</dt>
              <dd class="text-gray-900 dark:text-white col-span-2 font-mono">{{ form.tableName }}</dd>
            </div>
            <div class="py-2 grid grid-cols-3 gap-4">
              <dt class="text-gray-500 dark:text-gray-400">Champs</dt>
              <dd class="text-gray-900 dark:text-white col-span-2">{{ selectedFieldCount }} selectionne(s)</dd>
            </div>
            <div v-if="form.tableDescription" class="py-2 grid grid-cols-3 gap-4">
              <dt class="text-gray-500 dark:text-gray-400">Description</dt>
              <dd class="text-gray-900 dark:text-white col-span-2 whitespace-pre-wrap">{{ form.tableDescription }}</dd>
            </div>
          </dl>
        </div>

        <!-- Footer actions -->
        <div class="mt-6 flex justify-between gap-3 pt-4 border-t border-gray-100 dark:border-gray-800">
          <button
            v-if="currentStep > 0"
            type="button"
            class="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-white/5 rounded-md hover:bg-gray-200 dark:hover:bg-gray-700"
            @click="goBack"
          >
            Precedent
          </button>
          <div v-else />
          <div class="flex gap-3">
            <button
              type="button"
              class="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-white/5 rounded-md hover:bg-gray-200 dark:hover:bg-gray-700"
              @click="handleClose"
            >
              Annuler
            </button>
            <button
              v-if="currentStep < lastStepIndex"
              type="button"
              class="px-4 py-2 text-sm font-medium text-white bg-brand-500 rounded-md hover:bg-brand-600 disabled:opacity-50"
              :disabled="!canGoNext"
              @click="goNext"
            >
              Suivant
            </button>
            <button
              v-else
              type="button"
              class="px-4 py-2 text-sm font-medium text-white bg-brand-500 rounded-md hover:bg-brand-600 disabled:opacity-50"
              :disabled="submitting || selectedFieldCount === 0"
              @click="handleSubmit"
            >
              <i v-if="submitting" class="pi pi-spinner pi-spin mr-1" />
              Confirmer
            </button>
          </div>
        </div>
      </DialogContent>
    </DialogPortal>
  </DialogRoot>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch } from 'vue';
import {
  DialogRoot,
  DialogPortal,
  DialogOverlay,
  DialogContent,
  DialogTitle,
  DialogDescription,
} from 'radix-vue';
import StepTabs from '@/components/shared/StepTabs.vue';
import { bddApi } from '@/api/bdd';
import { HELLOPRO_DATABASES } from '@/types/bdd';
import type { BDDCatalogTable, BDDCatalogField, BDDUsedTable } from '@/types/bdd';
import { useToast } from '@/composables/useToast';
import { ApiError } from '@/types/api';

const props = defineProps<{
  open: boolean;
  defaultDatabaseId: number;
  existingTables: BDDUsedTable[];
}>();

const emit = defineEmits<{
  'update:open': [value: boolean];
  created: [table: BDDUsedTable];
}>();

const toast = useToast();

const databases = HELLOPRO_DATABASES;
const stepLabels = ['Base', 'Table', 'Champs', 'Description', 'Recap'];
const lastStepIndex = stepLabels.length - 1;

const currentStep = ref(0);
const submitting = ref(false);

const form = reactive({
  databaseId: props.defaultDatabaseId,
  catalogTableId: undefined as number | undefined,
  tableName: '',
  tableDescription: '',
});

const catalogSearch = ref('');
const catalogTables = ref<BDDCatalogTable[]>([]);
const catalogFields = ref<BDDCatalogField[]>([]);
const fieldSelections = reactive<Record<number, boolean>>({});
const fieldCuratedDescriptions = reactive<Record<number, string>>({});
const fieldDescriptionsOpen = reactive<Record<number, boolean>>({});

const loadingCatalog = ref(false);
const loadingFields = ref(false);
const catalogUnavailable = ref(false);
const fieldsUnavailable = ref(false);
const step1Error = ref<'' | 'duplicate'>('');

let searchDebounce: ReturnType<typeof setTimeout> | undefined;

const selectedDatabaseName = computed(() => {
  return databases.find((d) => d.id === form.databaseId)?.name || '';
});

const selectedFieldCount = computed(() => {
  return Object.values(fieldSelections).filter(Boolean).length;
});

const canGoNext = computed(() => {
  if (currentStep.value === 0) return form.databaseId !== undefined;
  if (currentStep.value === 1) return !!form.catalogTableId && step1Error.value !== 'duplicate';
  if (currentStep.value === 2) return selectedFieldCount.value > 0;
  return true;
});

const completedSteps = computed(() => {
  const steps: number[] = [];
  if (form.databaseId !== undefined) steps.push(0);
  if (form.catalogTableId) steps.push(1);
  if (selectedFieldCount.value > 0) steps.push(2);
  return steps;
});

watch(
  () => props.open,
  (open) => {
    if (open) {
      resetForm();
    }
  },
);

watch(
  () => props.defaultDatabaseId,
  (id) => {
    if (props.open) {
      form.databaseId = id;
    }
  },
);

watch(catalogSearch, () => {
  if (currentStep.value !== 1) return;
  if (searchDebounce) clearTimeout(searchDebounce);
  searchDebounce = setTimeout(() => {
    loadCatalogTables();
  }, 300);
});

function resetForm() {
  currentStep.value = 0;
  form.databaseId = props.defaultDatabaseId;
  form.catalogTableId = undefined;
  form.tableName = '';
  form.tableDescription = '';
  catalogSearch.value = '';
  catalogTables.value = [];
  catalogFields.value = [];
  Object.keys(fieldSelections).forEach((k) => delete fieldSelections[Number(k)]);
  Object.keys(fieldCuratedDescriptions).forEach((k) => delete fieldCuratedDescriptions[Number(k)]);
  Object.keys(fieldDescriptionsOpen).forEach((k) => delete fieldDescriptionsOpen[Number(k)]);
  catalogUnavailable.value = false;
  fieldsUnavailable.value = false;
  step1Error.value = '';
}

function handleOpenChange(value: boolean) {
  if (!value) {
    handleClose();
  }
}

function handleClose() {
  emit('update:open', false);
}

function selectDatabase(id: number) {
  form.databaseId = id;
  form.catalogTableId = undefined;
  catalogTables.value = [];
}

function isAlreadyRegistered(t: BDDCatalogTable): boolean {
  return props.existingTables.some(
    (e) => e.database_id === form.databaseId && e.table_name === t.table_name,
  );
}

function selectCatalogTable(t: BDDCatalogTable) {
  if (isAlreadyRegistered(t)) {
    step1Error.value = 'duplicate';
    return;
  }
  step1Error.value = '';
  form.catalogTableId = t.id;
  form.tableName = t.table_name;
}

async function loadCatalogTables() {
  loadingCatalog.value = true;
  catalogUnavailable.value = false;
  try {
    const res = await bddApi.catalogTables(form.databaseId, catalogSearch.value.trim());
    catalogTables.value = res.tables || [];
  } catch (err) {
    if (err instanceof ApiError && err.status === 503) {
      catalogUnavailable.value = true;
      catalogTables.value = [];
    } else {
      toast.error('Impossible de charger le catalogue');
    }
  } finally {
    loadingCatalog.value = false;
  }
}

async function loadCatalogFields() {
  if (!form.catalogTableId) return;
  loadingFields.value = true;
  fieldsUnavailable.value = false;
  try {
    const res = await bddApi.catalogFields(form.databaseId, form.catalogTableId);
    catalogFields.value = res.fields || [];
    Object.keys(fieldSelections).forEach((k) => delete fieldSelections[Number(k)]);
  } catch (err) {
    if (err instanceof ApiError && err.status === 503) {
      fieldsUnavailable.value = true;
      catalogFields.value = [];
    } else {
      toast.error('Impossible de charger les champs');
    }
  } finally {
    loadingFields.value = false;
  }
}

function toggleField(f: BDDCatalogField) {
  if (fieldSelections[f.id]) {
    delete fieldSelections[f.id];
    delete fieldDescriptionsOpen[f.id];
  } else {
    fieldSelections[f.id] = true;
  }
}

function selectAllFields() {
  catalogFields.value.forEach((f) => {
    fieldSelections[f.id] = true;
  });
}

function deselectAllFields() {
  Object.keys(fieldSelections).forEach((k) => delete fieldSelections[Number(k)]);
  Object.keys(fieldDescriptionsOpen).forEach((k) => delete fieldDescriptionsOpen[Number(k)]);
}

function toggleFieldDescriptionEdit(id: number) {
  fieldDescriptionsOpen[id] = !fieldDescriptionsOpen[id];
}

function goToStep(step: number) {
  if (step < currentStep.value || completedSteps.value.includes(step)) {
    currentStep.value = step;
    onEnterStep(step);
  }
}

function goNext() {
  if (!canGoNext.value || currentStep.value >= lastStepIndex) return;
  currentStep.value++;
  onEnterStep(currentStep.value);
}

function goBack() {
  if (currentStep.value > 0) {
    currentStep.value--;
  }
}

function onEnterStep(step: number) {
  if (step === 1 && catalogTables.value.length === 0 && !catalogUnavailable.value) {
    loadCatalogTables();
  }
  if (step === 2 && form.catalogTableId && catalogFields.value.length === 0 && !fieldsUnavailable.value) {
    loadCatalogFields();
  }
}

async function handleSubmit() {
  if (selectedFieldCount.value === 0) return;
  submitting.value = true;
  step1Error.value = '';
  try {
    const fields = catalogFields.value
      .filter((f) => fieldSelections[f.id])
      .map((f) => ({
        field_name: f.field_name,
        description: fieldCuratedDescriptions[f.id]?.trim() || undefined,
        upstream_field_id: f.id,
      }));
    const body = {
      database_id: form.databaseId,
      table_name: form.tableName,
      description: form.tableDescription.trim() || undefined,
      upstream_table_id: form.catalogTableId,
      fields,
    };
    const created = await bddApi.createUsed(body);
    toast.success('Table ajoutee');
    emit('created', created);
    emit('update:open', false);
  } catch (err) {
    if (err instanceof ApiError && err.status === 409) {
      step1Error.value = 'duplicate';
      currentStep.value = 1;
    } else {
      toast.error(err instanceof Error ? err.message : 'Erreur lors de la creation');
    }
  } finally {
    submitting.value = false;
  }
}
</script>
