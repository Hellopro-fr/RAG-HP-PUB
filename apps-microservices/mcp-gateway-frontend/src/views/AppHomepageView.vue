<template>
  <div class="min-h-screen bg-white dark:bg-gray-950">
    <div class="max-w-3xl mx-auto px-6 py-12">
      <!-- Header -->
      <div class="text-center mb-12">
        <div class="inline-flex items-center gap-3 mb-4">
          <img src="/images/servers/hp-logo.svg" alt="Hellopro" class="w-10 h-10" />
          <h1 class="text-3xl font-bold text-gray-900 dark:text-white">MCP Gateway</h1>
        </div>
        <p class="text-lg text-gray-600 dark:text-gray-400">
          Plateforme d'agrégation de serveurs MCP par HelloPro
        </p>
      </div>

      <div class="space-y-8 text-sm text-gray-700 dark:text-gray-300">
        <!-- What is it -->
        <section class="rounded-xl border border-gray-200 dark:border-gray-800 p-6">
          <h2 class="text-lg font-semibold text-gray-900 dark:text-white mb-3">
            <i class="pi pi-info-circle mr-2 text-brand-500" />
            Qu'est-ce que MCP Gateway ?
          </h2>
          <p>
            MCP Gateway est un service interne d'<strong>HelloPro</strong> qui centralise et route les requêtes
            entre plusieurs serveurs MCP (Model Context Protocol). Il fournit une interface unifiée pour découvrir
            et utiliser les outils, ressources et prompts exposés par chaque serveur.
          </p>
        </section>

        <!-- Fonctionnalités -->
        <section class="rounded-xl border border-gray-200 dark:border-gray-800 p-6">
          <h2 class="text-lg font-semibold text-gray-900 dark:text-white mb-3">
            <i class="pi pi-list mr-2 text-brand-500" />
            Fonctionnalités
          </h2>
          <ul class="list-disc pl-5 space-y-2">
            <li><strong>Agrégation MCP</strong> — connexion unifiée à de multiples serveurs MCP</li>
            <li><strong>Administration</strong> — interface pour gérer les serveurs, tokens d'accès et clients OAuth2</li>
            <li><strong>Import Google Sheets</strong> — import de serveurs depuis vos feuilles de calcul Google (lecture seule)</li>
            <li><strong>Contrôle d'accès</strong> — tokens scoped et OAuth2 pour restreindre l'accès aux outils</li>
            <li><strong>Monitoring</strong> — health checks automatiques et journal d'audit</li>
          </ul>
        </section>

        <!-- Google data usage -->
        <section class="rounded-xl border border-gray-200 dark:border-gray-800 p-6">
          <h2 class="text-lg font-semibold text-gray-900 dark:text-white mb-3">
            <i class="pi pi-google mr-2 text-brand-500" />
            Utilisation des données Google
          </h2>
          <p class="mb-3">
            MCP Gateway demande un accès <strong>en lecture seule</strong> à vos Google Spreadsheets pour permettre
            l'import de configurations de serveurs MCP. Nous accédons uniquement aux scopes suivants :
          </p>
          <ul class="list-disc pl-5 space-y-1 mb-3">
            <li><code class="text-xs bg-gray-100 dark:bg-gray-800 px-1 py-0.5 rounded">spreadsheets.readonly</code> — lire le contenu de vos feuilles</li>
            <li><code class="text-xs bg-gray-100 dark:bg-gray-800 px-1 py-0.5 rounded">drive.readonly</code> — lister vos fichiers Spreadsheet</li>
          </ul>
          <p>
            Vos données Google ne sont <strong>jamais modifiées, partagées ou vendues</strong>.
            Vous pouvez révoquer l'accès à tout moment depuis les paramètres de votre compte.
          </p>
        </section>

        <!-- Links -->
        <section class="rounded-xl border border-gray-200 dark:border-gray-800 p-6">
          <h2 class="text-lg font-semibold text-gray-900 dark:text-white mb-3">
            <i class="pi pi-link mr-2 text-brand-500" />
            Liens
          </h2>
          <ul class="space-y-2">
            <li>
              <router-link to="/privacy" class="text-brand-500 hover:text-brand-600">
                <i class="pi pi-shield mr-1" /> Politique de confidentialité
              </router-link>
            </li>
            <li>
              <a href="https://www.hellopro.fr" target="_blank" rel="noopener" class="text-brand-500 hover:text-brand-600">
                <i class="pi pi-external-link mr-1" /> HelloPro.fr
              </a>
            </li>
          </ul>
        </section>
      </div>

      <div class="mt-12 pt-6 border-t border-gray-200 dark:border-gray-800 text-center text-xs text-gray-400 dark:text-gray-500">
        © {{ new Date().getFullYear() }} HelloPro — MCP Gateway
      </div>
    </div>
  </div>
</template>
