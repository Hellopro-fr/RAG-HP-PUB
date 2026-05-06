<template>
  <div>
    <PageBreadcrumb page-title="Configuration de la table" />

    <!-- Loading state -->
    <div v-if="loading" class="text-center py-12">
      <i class="pi pi-spinner pi-spin text-2xl text-brand-500" />
    </div>

    <!-- Not found state -->
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

    <!-- Main content -->
    <div
      v-else
      class="rounded-2xl border border-gray-200 bg-white dark:border-gray-800 dark:bg-white/[0.03]"
    >
      <!-- Header -->
      <header
        class="flex flex-wrap items-start justify-between gap-3 border-b border-gray-100 px-6 py-5 dark:border-gray-800"
      >
        <div class="min-w-0">
          <h1
            class="text-xl font-mono font-semibold text-gray-900 dark:text-white truncate"
          >
            {{ table.table_name }}
          </h1>
          <p class="mt-1 text-sm text-gray-500 dark:text-gray-400">
            {{ databaseName(table.database_id) }}
          </p>
        </div>
        <div class="flex items-center gap-2 shrink-0">
          <span
            v-if="hasFields"
            class="inline-flex items-center rounded-full bg-success-50 px-2.5 py-0.5 text-xs font-medium text-success-700 dark:bg-success-500/15 dark:text-success-400"
          >
            <i class="pi pi-check-circle text-[10px] mr-1" />
            Actif
          </span>
          <span
            v-else
            class="inline-flex items-center rounded-full bg-warning-50 px-2.5 py-0.5 text-xs font-medium text-warning-700 dark:bg-warning-500/15 dark:text-warning-400"
          >
            <i class="pi pi-exclamation-triangle text-[10px] mr-1" />
            Non actif
          </span>
        </div>
      </header>

      <!-- Inactive banner -->
      <div
        v-if="!hasFields"
        class="mx-6 mt-5 rounded-lg border border-warning-200 bg-warning-50 px-4 py-3 text-sm text-warning-800 dark:border-warning-500/30 dark:bg-warning-500/10 dark:text-warning-300"
      >
        <i class="pi pi-info-circle mr-2" />
        Cette table est inactive. Ajoutez au moins un champ pour l'activer.
      </div>

      <!-- Import / export (inline) -->
      <div v-if="isAdmin" class="px-6 pt-5">
        <JsonImportExport
          :busy="importing"
          @export="exportTable"
          @import-file="handleImportFile"
        />
        <p
          v-if="importError"
          class="mt-2 text-xs text-error-500"
        >
          {{ importError }}
        </p>
      </div>

      <!-- Description section -->
      <section class="px-6 py-5">
        <div class="flex items-center justify-between mb-2">
          <label
            class="text-sm font-medium text-gray-700 dark:text-gray-300"
          >
            Description de la table
          </label>
          <button
            v-if="isAdmin"
            type="button"
            :disabled="!dirtyDescription || savingDescription"
            class="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-white bg-brand-500 rounded-md hover:bg-brand-600 disabled:opacity-50 disabled:cursor-not-allowed"
            @click="saveDescription"
          >
            <i
              v-if="savingDescription"
              class="pi pi-spinner pi-spin text-[10px]"
            />
            <i v-else class="pi pi-save text-[10px]" />
            Enregistrer la description
          </button>
        </div>
        <WysiwygEditor
          v-if="isAdmin"
          v-model="descriptionDraft"
          placeholder="Description fonctionnelle de la table (utilisee dans la doc LLM)"
        />
        <div
          v-else
          class="rounded-lg border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800/50 px-3 py-2 text-sm text-gray-700 dark:text-gray-300 prose prose-sm max-w-none dark:prose-invert"
          v-safe-html="descriptionDraft || '<em class=\'text-gray-400\'>Aucune description</em>'"
        />
      </section>

      <!-- Metadata section -->
      <section class="px-6 pb-2">
        <div class="flex items-center justify-between mb-3">
          <div>
            <h3 class="text-sm font-semibold text-gray-900 dark:text-white">
              Metadonnees
            </h3>
            <p class="text-[11px] text-gray-500 dark:text-gray-400 mt-0.5">
              Champs structures injectes dans la doc generee par bdd_get_table_doc.
            </p>
          </div>
          <button
            v-if="isAdmin"
            type="button"
            :disabled="!metaDirty || savingMeta"
            class="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-white bg-brand-500 rounded-md hover:bg-brand-600 disabled:opacity-50 disabled:cursor-not-allowed"
            @click="saveMetadata"
          >
            <i
              v-if="savingMeta"
              class="pi pi-spinner pi-spin text-[10px]"
            />
            <i v-else class="pi pi-save text-[10px]" />
            Enregistrer les metadonnees
          </button>
        </div>
        <div class="grid grid-cols-1 md:grid-cols-3 gap-3">
          <div>
            <label
              class="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1"
            >
              Cle primaire
              <span class="text-[10px] text-gray-400 ml-1">(catalogue)</span>
            </label>
            <div
              class="h-9 w-full flex items-center rounded-md border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800/50 px-3 text-sm font-mono text-gray-700 dark:text-gray-300"
            >
              <span v-if="table?.primary_key" class="truncate">
                {{ table.primary_key }}
              </span>
              <span v-else class="text-xs text-gray-400 italic">
                Non defini par le catalogue
              </span>
            </div>
          </div>
          <div>
            <label
              class="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1"
            >
              ORDER BY par defaut
            </label>
            <input
              v-model="metaDraft.default_order_by"
              :readonly="!isAdmin"
              type="text"
              maxlength="255"
              placeholder="ex: date_creation_lead DESC"
              class="h-9 w-full rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm font-mono dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200"
            />
          </div>
          <div>
            <label
              class="flex items-center justify-between text-xs font-medium text-gray-500 dark:text-gray-400 mb-1"
            >
              <span>
                Nombre de lignes
                <span class="text-[10px] text-gray-400 ml-1">(catalogue)</span>
              </span>
              <span v-if="isAdmin" class="inline-flex items-center gap-2">
                <button
                  type="button"
                  :disabled="savingRows || !rowsDirty || rowsDraft === ''"
                  class="inline-flex items-center gap-1 px-1.5 py-0.5 text-[10px] font-medium text-success-700 hover:text-success-800 disabled:opacity-50 disabled:cursor-not-allowed dark:text-success-400"
                  title="Sauvegarder le compte saisi en base"
                  @click="saveRowsManual"
                >
                  <i
                    :class="savingRows ? 'pi pi-spinner pi-spin' : 'pi pi-save'"
                    class="text-[10px]"
                  />
                  Enregistrer
                </button>
                <button
                  type="button"
                  :disabled="refreshingCatalog || !table?.upstream_table_id"
                  class="inline-flex items-center gap-1 px-1.5 py-0.5 text-[10px] font-medium text-brand-600 hover:text-brand-700 disabled:opacity-50 disabled:cursor-not-allowed dark:text-brand-400"
                  title="Re-synchroniser depuis le catalogue"
                  @click="refreshFromCatalog"
                >
                  <i
                    :class="refreshingCatalog ? 'pi pi-spinner pi-spin' : 'pi pi-refresh'"
                    class="text-[10px]"
                  />
                  Actualiser
                </button>
              </span>
            </label>
            <input
              v-if="isAdmin"
              v-model.number="rowsDraft"
              type="number"
              min="0"
              step="1"
              placeholder="Saisir le nombre de lignes"
              class="h-9 w-full rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm font-mono dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200"
            />
            <div
              v-else
              class="h-9 w-full flex items-center rounded-md border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800/50 px-3 text-sm text-gray-700 dark:text-gray-300"
            >
              <span v-if="table?.rows != null">
                {{ table.rows.toLocaleString('fr-FR') }}
              </span>
              <span v-else class="text-xs text-gray-400 italic">
                Non synchronise
              </span>
            </div>
            <p
              v-if="isAdmin && rowsError"
              class="mt-1 text-[11px] text-error-500"
            >
              {{ rowsError }}
            </p>
          </div>
        </div>
        <div class="mt-3">
          <label
            class="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1"
          >
            Notes
          </label>
          <textarea
            v-model="metaDraft.notes"
            :readonly="!isAdmin"
            rows="2"
            maxlength="4096"
            placeholder="Remarques operationnelles, contraintes, conseils..."
            class="w-full rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200"
          />
        </div>
        <div class="mt-3">
          <div class="flex items-center justify-between mb-1">
            <label
              class="block text-xs font-medium text-gray-500 dark:text-gray-400"
            >
              Relations
            </label>
            <button
              v-if="isAdmin && hasLinkableTables"
              type="button"
              class="inline-flex items-center gap-1 px-2 py-1 text-[11px] font-medium text-brand-600 hover:text-brand-700 dark:text-brand-400"
              @click="addRelationRow"
            >
              <i class="pi pi-plus text-[10px]" />
              Ajouter une relation
            </button>
          </div>
          <div
            v-if="!hasLinkableTables"
            class="rounded-md border border-warning-200 dark:border-warning-500/30 bg-warning-50 dark:bg-warning-500/10 px-3 py-2 text-xs text-warning-800 dark:text-warning-300"
          >
            <i class="pi pi-info-circle mr-1" />
            Aucune autre table active disponible. Les relations seront
            activables des qu'au moins une autre table (avec au moins un champ)
            sera enregistree.
          </div>
          <template v-else>
          <div
            v-if="metaDraft.relations.length === 0"
            class="rounded-md border-2 border-dashed border-gray-200 dark:border-gray-700 px-3 py-3 text-center text-xs text-gray-400"
          >
            Aucune relation. Cliquez sur "Ajouter une relation" pour creer un
            lien vers une autre table active.
          </div>
          <div v-else class="space-y-3">
            <BDDRelationBlock
              v-for="(row, idx) in metaDraft.relations"
              :key="idx"
              :model-value="row"
              :self-table-name="table?.table_name ?? ''"
              :fields="fields"
              :available-target-tables="availableTargetTables"
              :is-admin="isAdmin"
              :index="idx"
              :default-expanded="!row.self_col || !row.target_table || !row.target_col"
              @update:model-value="(v) => onRelationUpdate(idx, v)"
              @remove="removeRelationRow(idx)"
            />
          </div>
          <p
            v-if="relationsParseError"
            class="text-[11px] text-error-500 mt-1"
          >
            {{ relationsParseError }}
          </p>
          <p class="text-[11px] text-gray-400 mt-1">
            Une seule relation par table cible. Les doublons seront ecrases lors
            de l'enregistrement.
          </p>
          </template>
        </div>
      </section>

      <!-- Fields section -->
      <section class="px-6 pb-6">
        <div class="flex items-center justify-between mb-2">
          <div>
            <h3 class="text-sm font-semibold text-gray-900 dark:text-white">
              Champs
              <span class="text-xs font-normal text-gray-500 ml-1">
                ({{ fields.length }})
              </span>
            </h3>
            <p class="text-[11px] text-gray-500 dark:text-gray-400 mt-0.5">
              L'ordre est local pour le moment et sera persiste plus tard.
            </p>
          </div>
          <button
            v-if="isAdmin"
            type="button"
            class="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-white bg-brand-500 rounded-md hover:bg-brand-600"
            @click="showAddField = !showAddField"
          >
            <i :class="showAddField ? 'pi pi-times' : 'pi pi-plus'" class="text-[10px]" />
            {{ showAddField ? 'Annuler' : 'Ajouter un champ' }}
          </button>
        </div>

        <!-- Add-field inline form -->
        <div
          v-if="isAdmin && showAddField"
          class="mb-3 rounded-lg border border-brand-200 dark:border-brand-500/40 bg-brand-50/40 dark:bg-brand-500/5 p-4"
        >
          <!-- Catalog-driven multi-select -->
          <template v-if="hasCatalogPicker">
            <div class="flex items-center justify-between gap-2 mb-2">
              <input
                v-model="newFieldSearch"
                type="text"
                placeholder="Filtrer par nom de champ"
                class="h-8 flex-1 rounded-md border border-gray-300 bg-white px-3 text-sm dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200"
              />
              <span class="text-xs text-gray-500 dark:text-gray-400 shrink-0">
                {{ selectedNewFields.size }}/{{ filteredAvailableFields.length }}
              </span>
              <button
                type="button"
                class="text-xs text-brand-500 hover:text-brand-600 dark:text-brand-400 shrink-0"
                @click="toggleAllAvailable"
              >
                {{ allFilteredSelected ? 'Tout deselectionner' : 'Tout selectionner' }}
              </button>
            </div>
            <div
              class="max-h-64 overflow-y-auto divide-y divide-gray-100 dark:divide-gray-800 border border-gray-200 dark:border-gray-700 rounded-md bg-white dark:bg-gray-900"
            >
              <label
                v-for="opt in filteredAvailableFields"
                :key="opt.id"
                class="flex items-start gap-2 px-3 py-2 text-sm text-gray-700 dark:text-gray-300 cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800/50"
              >
                <input
                  type="checkbox"
                  class="mt-0.5 rounded border-gray-300 text-brand-500 dark:border-gray-700"
                  :checked="selectedNewFields.has(opt.field_name)"
                  @change="toggleNewField(opt.field_name, ($event.target as HTMLInputElement).checked)"
                />
                <span class="flex-1 min-w-0">
                  <code class="font-mono text-[13px]">{{ opt.field_name }}</code>
                  <span
                    v-if="opt.field_type"
                    class="text-xs text-gray-400 dark:text-gray-500 ml-1"
                  >
                    ({{ opt.field_type }}<template v-if="opt.is_nullable">, null</template>)
                  </span>
                  <span
                    v-if="opt.description"
                    class="block text-xs text-gray-400 dark:text-gray-500 truncate"
                    :title="opt.description"
                  >
                    {{ opt.description }}
                  </span>
                </span>
              </label>
              <div
                v-if="filteredAvailableFields.length === 0"
                class="px-3 py-3 text-sm text-gray-400 dark:text-gray-500 text-center"
              >
                Aucun champ disponible.
              </div>
            </div>
            <div class="mt-3 flex items-center gap-2">
              <button
                type="button"
                :disabled="selectedNewFields.size === 0 || addingField"
                class="px-3 py-1.5 text-xs font-medium text-white bg-brand-500 rounded-md hover:bg-brand-600 disabled:opacity-50 disabled:cursor-not-allowed"
                @click="submitNewFields"
              >
                <i
                  v-if="addingField"
                  class="pi pi-spinner pi-spin text-[10px] mr-1"
                />
                Ajouter ({{ selectedNewFields.size }})
              </button>
              <button
                type="button"
                class="px-3 py-1.5 text-xs font-medium text-gray-700 dark:text-gray-200 border border-gray-300 dark:border-gray-600 rounded-md hover:bg-gray-50 dark:hover:bg-gray-700"
                @click="resetNewFieldForm"
              >
                Reinitialiser
              </button>
              <p class="text-[11px] text-gray-400 ml-auto">
                Les descriptions s'editent apres ajout dans chaque bloc.
              </p>
            </div>
          </template>

          <!-- Manual fallback when catalog unavailable -->
          <template v-else>
            <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div>
                <label
                  class="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1"
                >
                  Nom du champ
                  <span class="text-error-500">*</span>
                </label>
                <input
                  v-model="newFieldName"
                  type="text"
                  maxlength="128"
                  placeholder="nom_du_champ"
                  class="h-9 w-full rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm font-mono dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200"
                />
                <p
                  v-if="newFieldName && !isValidFieldName"
                  class="text-[11px] text-error-500 mt-1"
                >
                  Caracteres autorises : a-z, A-Z, 0-9 et _ (1 a 128 caracteres).
                </p>
              </div>
              <div>
                <label
                  class="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1"
                >
                  Description (optionnelle)
                </label>
                <input
                  v-model="newFieldDescription"
                  type="text"
                  maxlength="2048"
                  placeholder="Courte description, ajustable apres ajout"
                  class="h-9 w-full rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200"
                />
              </div>
            </div>
            <div class="mt-3 flex items-center gap-2">
              <button
                type="button"
                :disabled="!canSubmitNewField || addingField"
                class="px-3 py-1.5 text-xs font-medium text-white bg-brand-500 rounded-md hover:bg-brand-600 disabled:opacity-50 disabled:cursor-not-allowed"
                @click="submitNewField"
              >
                <i
                  v-if="addingField"
                  class="pi pi-spinner pi-spin text-[10px] mr-1"
                />
                Ajouter
              </button>
              <button
                type="button"
                class="px-3 py-1.5 text-xs font-medium text-gray-700 dark:text-gray-200 border border-gray-300 dark:border-gray-600 rounded-md hover:bg-gray-50 dark:hover:bg-gray-700"
                @click="resetNewFieldForm"
              >
                Reinitialiser
              </button>
            </div>
          </template>
        </div>

        <!-- Empty state -->
        <div
          v-if="fields.length === 0"
          class="text-center py-10 text-gray-400 dark:text-gray-500 border-2 border-dashed border-gray-300 dark:border-gray-700 rounded-lg"
        >
          <i class="pi pi-inbox text-2xl mb-2 block" />
          <p class="text-sm">
            Aucun champ enregistre.
            <template v-if="isAdmin">
              Cliquez sur "Ajouter un champ" pour activer la table.
            </template>
          </p>
        </div>

        <!-- Field blocks -->
        <VueDraggable
          v-else
          v-model="fields"
          :animation="180"
          handle=".field-drag-handle"
          ghost-class="field-ghost"
          class="space-y-3"
          :disabled="!isAdmin"
        >
          <BDDFieldBlock
            v-for="(field, index) in fields"
            :key="field.id"
            :model-value="field"
            :catalog-field="catalogForField(field)"
            :is-admin="isAdmin"
            :index="index"
            @update:model-value="onFieldUpdate(field.id, $event)"
            @remove="deletingField = field"
          />
        </VueDraggable>

        <!-- Footer save bar -->
        <div
          v-if="dirtyFields.size > 0"
          class="sticky bottom-2 mt-4 flex items-center justify-between rounded-lg border border-brand-300 dark:border-brand-500/40 bg-brand-50 dark:bg-brand-500/10 px-4 py-3"
        >
          <span class="text-sm text-brand-800 dark:text-brand-200">
            {{ dirtyFields.size }} champ{{ dirtyFields.size > 1 ? 's' : '' }}
            modifie{{ dirtyFields.size > 1 ? 's' : '' }} non enregistre{{ dirtyFields.size > 1 ? 's' : '' }}.
          </span>
          <div class="flex items-center gap-2">
            <button
              type="button"
              class="px-3 py-1.5 text-xs font-medium text-gray-700 dark:text-gray-200 border border-gray-300 dark:border-gray-600 rounded-md hover:bg-gray-50 dark:hover:bg-gray-700"
              @click="discardFieldChanges"
            >
              Annuler
            </button>
            <button
              type="button"
              :disabled="savingFields"
              class="px-3 py-1.5 text-xs font-medium text-white bg-brand-500 rounded-md hover:bg-brand-600 disabled:opacity-50 disabled:cursor-not-allowed"
              @click="saveDirtyFields"
            >
              <i
                v-if="savingFields"
                class="pi pi-spinner pi-spin text-[10px] mr-1"
              />
              Enregistrer les champs modifies ({{ dirtyFields.size }})
            </button>
          </div>
        </div>
      </section>
    </div>

    <!-- Delete-field confirm -->
    <ConfirmDialog
      :open="!!deletingField"
      title="Supprimer le champ"
      :message="
        deletingField
          ? 'Confirmer la suppression du champ \'' + deletingField.field_name + '\' ? Cette action est irreversible.'
          : ''
      "
      confirm-label="Supprimer"
      @update:open="deletingField = null"
      @confirm="confirmDeleteField"
    />

  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { VueDraggable } from 'vue-draggable-plus';
import { bddApi } from '@/api/bdd';
import {
  HELLOPRO_DATABASES,
  type BDDUsedTable,
  type BDDUsedField,
  type BDDCatalogField,
} from '@/types/bdd';
import { useAuthStore } from '@/stores/auth';
import { useToast } from '@/composables/useToast';
import { ApiError } from '@/types/api';
import PageBreadcrumb from '@/components/common/PageBreadcrumb.vue';
import WysiwygEditor from '@/components/shared/WysiwygEditor.vue';
import ConfirmDialog from '@/components/shared/ConfirmDialog.vue';
import BDDFieldBlock from '@/components/bdd/BDDFieldBlock.vue';
import BDDRelationBlock from '@/components/bdd/BDDRelationBlock.vue';
import JsonImportExport from '@/components/shared/JsonImportExport.vue';

const FIELD_NAME_RE = /^[a-zA-Z0-9_]{1,128}$/;

const route = useRoute();
const router = useRouter();
const authStore = useAuthStore();
const toast = useToast();

const id = computed(() => String(route.params.id));
const isAdmin = computed(() => authStore.isAdmin);

const table = ref<BDDUsedTable | null>(null);
const fields = ref<BDDUsedField[]>([]);
const loading = ref(true);

const descriptionDraft = ref('');
const savingDescription = ref(false);

interface RelationRow {
  self_col: string;
  target_table: string;
  target_col: string;
}

interface MetaDraft {
  default_order_by: string;
  notes: string;
  relations: RelationRow[];
}

const emptyMetaDraft = (): MetaDraft => ({
  default_order_by: '',
  notes: '',
  relations: [],
});

const metaDraft = ref<MetaDraft>(emptyMetaDraft());
const metaSnapshot = ref<MetaDraft>(emptyMetaDraft());
const savingMeta = ref(false);
const refreshingCatalog = ref(false);

// Manual rows override — admin can enter a row count and persist it
// without firing the upstream /count (which times out on huge tables).
const rowsDraft = ref<number | string>('');
const savingRows = ref(false);
const rowsError = ref<string | null>(null);
const rowsDirty = computed(() => {
  if (rowsDraft.value === '' || rowsDraft.value === null) return false;
  const n = Number(rowsDraft.value);
  if (!Number.isFinite(n) || n < 0) return false;
  return n !== (table.value?.rows ?? null);
});
const allRegisteredTables = ref<BDDUsedTable[]>([]);

const catalogByName = ref<Record<string, BDDCatalogField>>({});
const catalogUnavailable = ref(false);

const showAddField = ref(false);
const newFieldName = ref('');
const newFieldDescription = ref('');
const addingField = ref(false);

// Catalog-driven multi-select state.
const selectedNewFields = ref<Set<string>>(new Set());
const newFieldSearch = ref('');

const deletingField = ref<BDDUsedField | null>(null);

// Per-field dirty tracking — keyed by field.id, value = pending description.
const dirtyFields = ref<Set<string>>(new Set());
const pendingDescriptions = ref<Record<string, string>>({});
const savingFields = ref(false);

const importing = ref(false);
const importError = ref<string | null>(null);

const hasFields = computed(() => fields.value.length > 0);

const dirtyDescription = computed(
  () => descriptionDraft.value !== (table.value?.description ?? ''),
);

const metaDirty = computed(() => {
  const a = metaDraft.value;
  const b = metaSnapshot.value;
  return (
    a.default_order_by !== b.default_order_by ||
    a.notes !== b.notes ||
    JSON.stringify(a.relations) !== JSON.stringify(b.relations)
  );
});

const relationsParseError = ref<string | null>(null);

const RELATION_RE = /^\s*(\w+)\.(\w+)\s*->\s*(\w+)\.(\w+)\s*$/;

function parseRelationsValue(value: unknown): RelationRow[] {
  if (!value || Array.isArray(value)) return [];
  if (typeof value !== 'object') return [];
  const out: RelationRow[] = [];
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
}

function snapshotFromTable(t: BDDUsedTable): MetaDraft {
  return {
    default_order_by: t.default_order_by || '',
    notes: t.notes || '',
    relations: parseRelationsValue(t.relations),
  };
}

const availableTargetTables = computed(() => {
  const self = table.value?.table_name ?? '';
  return allRegisteredTables.value
    .filter((t) => t.table_name !== self && t.fields.length > 0)
    .slice()
    .sort((a, b) => a.table_name.localeCompare(b.table_name));
});

// hasLinkableTables: true when at least one OTHER active (with-fields)
// table exists. When false, the relations builder is meaningless and
// gets hidden entirely (admins still see the metadata block — just not
// the relations sub-section).
const hasLinkableTables = computed(
  () => availableTargetTables.value.length > 0,
);

function addRelationRow() {
  metaDraft.value.relations = [
    ...metaDraft.value.relations,
    { self_col: '', target_table: '', target_col: '' },
  ];
}

function removeRelationRow(idx: number) {
  const next = metaDraft.value.relations.slice();
  next.splice(idx, 1);
  metaDraft.value.relations = next;
}

function onRelationUpdate(
  idx: number,
  value: { self_col: string; target_table: string; target_col: string },
) {
  const next = metaDraft.value.relations.slice();
  next[idx] = value;
  metaDraft.value.relations = next;
}

async function loadAllRegisteredTables() {
  try {
    const res = await bddApi.listUsed({ limit: 100, page: 1 });
    allRegisteredTables.value = res.tables || [];
  } catch {
    allRegisteredTables.value = [];
  }
}

const hasCatalogPicker = computed(
  () => !catalogUnavailable.value && Object.keys(catalogByName.value).length > 0,
);

const availableCatalogFields = computed<BDDCatalogField[]>(() => {
  const taken = new Set(fields.value.map((f) => f.field_name));
  return Object.values(catalogByName.value)
    .filter((f) => !taken.has(f.field_name))
    .sort((a, b) => a.field_name.localeCompare(b.field_name));
});

const filteredAvailableFields = computed<BDDCatalogField[]>(() => {
  const q = newFieldSearch.value.trim().toLowerCase();
  if (!q) return availableCatalogFields.value;
  return availableCatalogFields.value.filter(
    (f) =>
      f.field_name.toLowerCase().includes(q) ||
      (f.field_type ? f.field_type.toLowerCase().includes(q) : false),
  );
});

const allFilteredSelected = computed(() => {
  const list = filteredAvailableFields.value;
  if (list.length === 0) return false;
  return list.every((f) => selectedNewFields.value.has(f.field_name));
});

const isValidFieldName = computed(() => FIELD_NAME_RE.test(newFieldName.value));

const canSubmitNewField = computed(
  () => isValidFieldName.value && !addingField.value,
);

function databaseName(dbId: number): string {
  return HELLOPRO_DATABASES.find((d) => d.id === dbId)?.name || '—';
}

function catalogForField(field: BDDUsedField): BDDCatalogField | null | undefined {
  if (catalogUnavailable.value) return null;
  return catalogByName.value[field.field_name];
}

async function loadTable() {
  loading.value = true;
  try {
    const res = await bddApi.getUsed(id.value);
    table.value = res;
    fields.value = [...(res.fields || [])];
    descriptionDraft.value = res.description || '';
    const snap = snapshotFromTable(res);
    metaDraft.value = { ...snap };
    metaSnapshot.value = snap;
    relationsParseError.value = null;
    dirtyFields.value = new Set();
    pendingDescriptions.value = {};
    rowsDraft.value = res.rows ?? '';
    rowsError.value = null;
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) {
      table.value = null;
    } else if (err instanceof ApiError && err.status === 503) {
      toast.error('Service BDD indisponible');
      table.value = null;
    } else {
      toast.error('Impossible de charger la table');
      table.value = null;
    }
  } finally {
    loading.value = false;
  }
}

async function loadCatalog() {
  if (!table.value || !table.value.upstream_table_id) {
    return;
  }
  try {
    const res = await bddApi.catalogFields(
      table.value.database_id,
      table.value.upstream_table_id,
    );
    const map: Record<string, BDDCatalogField> = {};
    for (const f of res.fields || []) {
      map[f.field_name] = f;
    }
    catalogByName.value = map;
    catalogUnavailable.value = false;
  } catch (err) {
    if (err instanceof ApiError && err.status === 503) {
      catalogUnavailable.value = true;
    } else {
      catalogUnavailable.value = true;
    }
  }
}

async function saveMetadata() {
  if (!table.value || !metaDirty.value || savingMeta.value) return;
  relationsParseError.value = null;

  // Serialise the row builder into the catalog's
  // {target_table: "self.col -> target_table.col"} shape. Empty rows
  // (missing self col, target table, or target col) are dropped silently
  // — the user can leave a half-filled row without it blocking save.
  const selfTableName = table.value.table_name;
  const rows = metaDraft.value.relations.filter(
    (r) => r.self_col && r.target_table && r.target_col,
  );
  let relationsValue: unknown;
  if (rows.length === 0) {
    relationsValue = [];
  } else {
    const obj: Record<string, string> = {};
    for (const r of rows) {
      obj[r.target_table] =
        selfTableName + '.' + r.self_col + ' -> ' + r.target_table + '.' + r.target_col;
    }
    relationsValue = obj;
  }

  savingMeta.value = true;
  try {
    const updated = await bddApi.patchUsed(id.value, {
      default_order_by: metaDraft.value.default_order_by,
      notes: metaDraft.value.notes,
      relations: relationsValue as never,
    });
    if (table.value) {
      table.value.default_order_by = updated.default_order_by;
      table.value.notes = updated.notes;
      table.value.relations = updated.relations;
    }
    metaSnapshot.value = snapshotFromTable(updated);
    metaDraft.value = { ...metaSnapshot.value };
    toast.success('Metadonnees enregistrees');
  } catch (err) {
    const body = (err as { body?: { error?: string } })?.body;
    const msg =
      body?.error || (err instanceof Error ? err.message : 'Erreur inconnue');
    toast.error('Echec de l\'enregistrement: ' + msg);
  } finally {
    savingMeta.value = false;
  }
}

async function refreshFromCatalog() {
  if (refreshingCatalog.value || !table.value) return;
  refreshingCatalog.value = true;
  try {
    const updated = await bddApi.refreshCatalog(id.value);
    if (table.value) {
      table.value.primary_key = updated.primary_key;
      table.value.rows = updated.rows;
    }
    rowsDraft.value = updated.rows ?? '';
    rowsError.value = null;
    toast.success('Synchronisation catalogue OK');
  } catch (err) {
    const body = (err as { body?: { error?: string } })?.body;
    const msg =
      body?.error || (err instanceof Error ? err.message : 'Erreur inconnue');
    toast.error('Echec de la synchronisation: ' + msg);
  } finally {
    refreshingCatalog.value = false;
  }
}

// Manual rows override: persists the integer typed in the input via
// PATCH (no upstream call). Useful when refresh-catalog times out on
// huge tables but the admin already knows the count.
async function saveRowsManual() {
  if (!table.value || savingRows.value) return;
  const n = Number(rowsDraft.value);
  if (!Number.isFinite(n) || n < 0 || !Number.isInteger(n)) {
    rowsError.value = 'Saisir un entier positif (>= 0).';
    return;
  }
  savingRows.value = true;
  rowsError.value = null;
  try {
    const updated = await bddApi.patchUsed(id.value, { rows: n });
    if (table.value) {
      table.value.rows = updated.rows;
    }
    rowsDraft.value = updated.rows ?? '';
    toast.success('Nombre de lignes enregistre');
  } catch (err) {
    const body = (err as { body?: { error?: string } })?.body;
    const msg =
      body?.error || (err instanceof Error ? err.message : 'Erreur inconnue');
    rowsError.value = msg;
    toast.error('Echec de la sauvegarde: ' + msg);
  } finally {
    savingRows.value = false;
  }
}

async function saveDescription() {
  if (!table.value || !dirtyDescription.value) return;
  savingDescription.value = true;
  try {
    const updated = await bddApi.patchUsed(id.value, {
      description: descriptionDraft.value,
    });
    if (table.value) {
      table.value.description = updated.description;
    }
    toast.success('Description enregistree');
  } catch (err) {
    const body = (err as { body?: { error?: string } })?.body;
    const msg =
      body?.error || (err instanceof Error ? err.message : 'Erreur inconnue');
    toast.error('Echec de l\'enregistrement: ' + msg);
  } finally {
    savingDescription.value = false;
  }
}

function resetNewFieldForm() {
  newFieldName.value = '';
  newFieldDescription.value = '';
  selectedNewFields.value = new Set();
  newFieldSearch.value = '';
}

function toggleNewField(name: string, checked: boolean) {
  const next = new Set(selectedNewFields.value);
  if (checked) next.add(name);
  else next.delete(name);
  selectedNewFields.value = next;
}

function toggleAllAvailable() {
  const list = filteredAvailableFields.value;
  if (list.length === 0) return;
  const next = new Set(selectedNewFields.value);
  if (allFilteredSelected.value) {
    list.forEach((f) => next.delete(f.field_name));
  } else {
    list.forEach((f) => next.add(f.field_name));
  }
  selectedNewFields.value = next;
}

async function submitNewField() {
  if (!canSubmitNewField.value) return;
  const upstream = catalogByName.value[newFieldName.value];
  addingField.value = true;
  try {
    const created = await bddApi.addField(id.value, {
      field_name: newFieldName.value,
      description: newFieldDescription.value || undefined,
      upstream_field_id: upstream?.id,
    });
    fields.value = [...fields.value, created];
    if (table.value) {
      table.value.fields = fields.value;
    }
    resetNewFieldForm();
    showAddField.value = false;
    toast.success('Champ ajoute');
  } catch (err) {
    const body = (err as { body?: { error?: string } })?.body;
    const msg =
      body?.error || (err instanceof Error ? err.message : 'Erreur inconnue');
    toast.error('Echec de l\'ajout: ' + msg);
  } finally {
    addingField.value = false;
  }
}

async function submitNewFields() {
  if (selectedNewFields.value.size === 0 || addingField.value) return;
  addingField.value = true;
  const names = Array.from(selectedNewFields.value);
  let okCount = 0;
  let errCount = 0;
  for (const name of names) {
    const upstream = catalogByName.value[name];
    try {
      const created = await bddApi.addField(id.value, {
        field_name: name,
        upstream_field_id: upstream?.id,
      });
      fields.value = [...fields.value, created];
      if (table.value) table.value.fields = fields.value;
      okCount++;
    } catch {
      errCount++;
    }
  }
  addingField.value = false;
  if (errCount === 0) {
    toast.success(okCount + ' champ(s) ajoute(s)');
    resetNewFieldForm();
    showAddField.value = false;
  } else {
    toast.error(okCount + ' ajoute(s), ' + errCount + ' erreur(s)');
    // Drop the ones that succeeded so retries only target failures.
    const taken = new Set(fields.value.map((f) => f.field_name));
    selectedNewFields.value = new Set(
      Array.from(selectedNewFields.value).filter((n) => !taken.has(n)),
    );
  }
}

function onFieldUpdate(fieldId: string, updated: BDDUsedField) {
  // Optimistically reflect description change locally + flag dirty.
  const idx = fields.value.findIndex((f) => f.id === fieldId);
  if (idx === -1) return;
  fields.value[idx] = updated;
  const original =
    table.value?.fields.find((f) => f.id === fieldId)?.description ?? '';
  if (updated.description === original) {
    dirtyFields.value.delete(fieldId);
    delete pendingDescriptions.value[fieldId];
  } else {
    dirtyFields.value.add(fieldId);
    pendingDescriptions.value[fieldId] = updated.description;
  }
  // Trigger reactivity for the Set.
  dirtyFields.value = new Set(dirtyFields.value);
}

function discardFieldChanges() {
  if (!table.value) return;
  // Restore field descriptions from the server snapshot.
  const original = new Map(table.value.fields.map((f) => [f.id, f]));
  fields.value = fields.value.map((f) => {
    const src = original.get(f.id);
    return src ? { ...f, description: src.description } : f;
  });
  dirtyFields.value = new Set();
  pendingDescriptions.value = {};
}

async function saveDirtyFields() {
  if (dirtyFields.value.size === 0) return;
  savingFields.value = true;
  const ids = Array.from(dirtyFields.value);
  let okCount = 0;
  let errCount = 0;
  for (const fid of ids) {
    const description = pendingDescriptions.value[fid] ?? '';
    try {
      const updated = await bddApi.patchField(id.value, fid, { description });
      const idx = fields.value.findIndex((f) => f.id === fid);
      if (idx !== -1) fields.value[idx] = updated;
      // Sync the canonical snapshot too.
      if (table.value) {
        const tIdx = table.value.fields.findIndex((f) => f.id === fid);
        if (tIdx !== -1) table.value.fields[tIdx] = updated;
      }
      dirtyFields.value.delete(fid);
      delete pendingDescriptions.value[fid];
      okCount++;
    } catch {
      errCount++;
    }
  }
  // Trigger reactivity for the Set.
  dirtyFields.value = new Set(dirtyFields.value);
  savingFields.value = false;
  if (errCount === 0) {
    toast.success(okCount + ' champ(s) enregistre(s)');
  } else {
    toast.error(okCount + ' enregistre(s), ' + errCount + ' erreur(s)');
  }
}

async function confirmDeleteField() {
  if (!deletingField.value) return;
  const target = deletingField.value;
  try {
    await bddApi.deleteField(id.value, target.id);
    fields.value = fields.value.filter((f) => f.id !== target.id);
    if (table.value) {
      table.value.fields = table.value.fields.filter((f) => f.id !== target.id);
    }
    dirtyFields.value.delete(target.id);
    delete pendingDescriptions.value[target.id];
    dirtyFields.value = new Set(dirtyFields.value);
    toast.success('Champ supprime');
  } catch {
    toast.error('Impossible de supprimer le champ');
  } finally {
    deletingField.value = null;
  }
}

// ----- Import / export (client-side per-table) -----

interface BDDExportedField {
  field_name: string;
  description?: string;
  upstream_field_id?: number;
}

interface BDDExportedTable {
  database_id: number;
  table_name: string;
  description?: string;
  upstream_table_id?: number;
  fields: BDDExportedField[];
}

interface BDDExportEnvelope {
  version: number;
  exported_at: string;
  table: BDDExportedTable;
}

function buildExportPayload(): BDDExportEnvelope | null {
  if (!table.value) return null;
  return {
    version: 1,
    exported_at: new Date().toISOString(),
    table: {
      database_id: table.value.database_id,
      table_name: table.value.table_name,
      description: table.value.description,
      upstream_table_id: table.value.upstream_table_id,
      fields: fields.value.map((f) => ({
        field_name: f.field_name,
        description: f.description,
        upstream_field_id: f.upstream_field_id,
      })),
    },
  };
}

function exportTable() {
  const payload = buildExportPayload();
  if (!payload || !table.value) return;
  const blob = new Blob([JSON.stringify(payload, null, 2)], {
    type: 'application/json',
  });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download =
    'bdd-table-' + table.value.database_id + '-' + table.value.table_name + '.json';
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
  toast.success('Export genere');
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
  let payload: BDDExportEnvelope;
  try {
    const text = await file.text();
    payload = JSON.parse(text) as BDDExportEnvelope;
  } catch {
    importError.value = 'Fichier JSON invalide.';
    importing.value = false;
    return;
  }
  if (!payload || !payload.table || !Array.isArray(payload.table.fields)) {
    importError.value = 'Structure JSON inattendue (table.fields manquant).';
    importing.value = false;
    return;
  }
  try {
    await applyImport(payload.table.fields);
    importError.value = null;
  } catch (err) {
    importError.value =
      'Echec de l\'import: ' +
      (err instanceof Error ? err.message : String(err));
  } finally {
    importing.value = false;
  }
}

async function applyImport(incoming: BDDExportedField[]) {
  let okCount = 0;
  let errCount = 0;
  for (const incomingField of incoming) {
    const name = (incomingField.field_name || '').trim();
    if (!FIELD_NAME_RE.test(name)) {
      errCount++;
      continue;
    }
    const existing = fields.value.find((f) => f.field_name === name);
    try {
      if (existing) {
        await bddApi.patchField(id.value, existing.id, {
          description: incomingField.description || '',
        });
      } else {
        await bddApi.addField(id.value, {
          field_name: name,
          description: incomingField.description,
          upstream_field_id: incomingField.upstream_field_id,
        });
      }
      okCount++;
    } catch {
      errCount++;
    }
  }
  // Reload from the server so the UI matches reality.
  await loadTable();
  if (errCount === 0) {
    toast.success(okCount + ' champ(s) importe(s)');
  } else {
    toast.error(okCount + ' importe(s), ' + errCount + ' erreur(s)');
  }
}

onMounted(async () => {
  if (!authStore.isAdmin) {
    router.replace('/tokens');
    return;
  }
  await Promise.all([loadTable(), loadAllRegisteredTables()]);
  if (table.value) {
    await loadCatalog();
  }
});

// If the route id changes (e.g. navigating between tables) re-fetch.
watch(id, async (next, prev) => {
  if (next && next !== prev) {
    catalogByName.value = {};
    catalogUnavailable.value = false;
    await Promise.all([loadTable(), loadAllRegisteredTables()]);
    if (table.value) {
      await loadCatalog();
    }
  }
});
</script>

<style scoped>
.field-ghost {
  opacity: 0.35;
  background: rgb(219 234 254);
}
</style>
