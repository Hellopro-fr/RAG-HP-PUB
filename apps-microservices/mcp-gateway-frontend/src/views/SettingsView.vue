<template>
  <div>
    <PageBreadcrumb page-title="Paramètres" />

    <div class="max-w-3xl mx-auto space-y-8 mt-6">
      <!-- Connected Accounts -->
      <section>
        <h2 class="text-lg font-semibold text-gray-900 dark:text-white mb-4">
          Comptes connectés
        </h2>
        <p class="text-sm text-gray-500 dark:text-gray-400 mb-4">
          Connectez vos comptes externes pour utiliser les fonctionnalités d'import.
        </p>
        <GoogleConnectCard />
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import PageBreadcrumb from '@/components/common/PageBreadcrumb.vue'
import GoogleConnectCard from '@/components/google/GoogleConnectCard.vue'
</script>
