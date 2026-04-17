<template>
  <div class="min-h-screen bg-white dark:bg-gray-950">
    <div class="max-w-3xl mx-auto px-6 py-12">
      <h1 class="text-3xl font-bold text-gray-900 dark:text-white mb-2">Politique de confidentialité</h1>
      <p class="text-sm text-gray-500 dark:text-gray-400 mb-8">Dernière mise à jour : 16 avril 2026</p>

      <div class="prose prose-gray dark:prose-invert max-w-none space-y-6 text-sm text-gray-700 dark:text-gray-300">
        <section>
          <h2 class="text-lg font-semibold text-gray-900 dark:text-white">1. Présentation</h2>
          <p>
            MCP Gateway est une plateforme d'agrégation de serveurs MCP (Model Context Protocol) développée par
            <strong>HelloPro</strong>. Cette politique décrit comment nous collectons, utilisons et protégeons
            vos données lorsque vous utilisez notre service.
          </p>
        </section>

        <section>
          <h2 class="text-lg font-semibold text-gray-900 dark:text-white">2. Données collectées</h2>
          <p>Nous collectons les données suivantes :</p>
          <ul class="list-disc pl-5 space-y-1">
            <li><strong>Informations de compte</strong> : adresse e-mail, nom d'affichage (fournis lors de la connexion).</li>
            <li><strong>Données Google (optionnel)</strong> : lorsque vous connectez votre compte Google pour l'import de feuilles de calcul, nous accédons en lecture seule à la liste et au contenu de vos Google Spreadsheets. Nous ne modifions jamais vos documents.</li>
            <li><strong>Journaux d'activité</strong> : actions effectuées dans l'interface d'administration (audit).</li>
          </ul>
        </section>

        <section>
          <h2 class="text-lg font-semibold text-gray-900 dark:text-white">3. Utilisation des données Google</h2>
          <p>
            L'accès à vos données Google est limité aux scopes suivants :
          </p>
          <ul class="list-disc pl-5 space-y-1">
            <li><code class="text-xs bg-gray-100 dark:bg-gray-800 px-1 py-0.5 rounded">spreadsheets.readonly</code> — lecture seule de vos feuilles de calcul Google Sheets.</li>
            <li><code class="text-xs bg-gray-100 dark:bg-gray-800 px-1 py-0.5 rounded">drive.readonly</code> — liste de vos fichiers Google Drive (uniquement les Spreadsheets).</li>
          </ul>
          <p>
            Ces données sont utilisées <strong>uniquement</strong> pour importer des configurations de serveurs MCP
            depuis vos feuilles de calcul. Vos tokens Google sont chiffrés (AES-256-GCM) et stockés de manière sécurisée.
            Vous pouvez déconnecter votre compte Google à tout moment depuis la page Paramètres, ce qui supprime
            immédiatement tous les tokens stockés.
          </p>
        </section>

        <section>
          <h2 class="text-lg font-semibold text-gray-900 dark:text-white">4. Stockage et sécurité</h2>
          <ul class="list-disc pl-5 space-y-1">
            <li>Les données sont stockées dans une base MySQL hébergée sur nos serveurs.</li>
            <li>Les tokens d'authentification et en-têtes sensibles sont chiffrés avec AES-256-GCM.</li>
            <li>L'accès à l'interface d'administration est protégé par authentification JWT.</li>
            <li>Les communications sont chiffrées via HTTPS.</li>
          </ul>
        </section>

        <section>
          <h2 class="text-lg font-semibold text-gray-900 dark:text-white">5. Partage des données</h2>
          <p>
            Nous ne vendons, ne louons ni ne partageons vos données personnelles avec des tiers.
            Vos données Google ne sont jamais transmises à des services externes autres que l'API Google elle-même.
          </p>
        </section>

        <section>
          <h2 class="text-lg font-semibold text-gray-900 dark:text-white">6. Conservation</h2>
          <p>
            Vos données sont conservées tant que votre compte est actif. Vous pouvez demander la suppression
            de vos données à tout moment en contactant l'administrateur.
          </p>
        </section>

        <section>
          <h2 class="text-lg font-semibold text-gray-900 dark:text-white">7. Vos droits</h2>
          <p>Conformément au RGPD, vous disposez des droits suivants :</p>
          <ul class="list-disc pl-5 space-y-1">
            <li>Droit d'accès à vos données personnelles</li>
            <li>Droit de rectification</li>
            <li>Droit à l'effacement</li>
            <li>Droit à la portabilité</li>
            <li>Droit de déconnecter votre compte Google à tout moment</li>
          </ul>
        </section>

        <section>
          <h2 class="text-lg font-semibold text-gray-900 dark:text-white">8. Contact</h2>
          <p>
            Pour toute question relative à cette politique de confidentialité, contactez-nous à :
            <a href="mailto:contact@hellopro.fr" class="text-brand-500 hover:text-brand-600">contact@hellopro.fr</a>
          </p>
        </section>
      </div>

      <div class="mt-12 pt-6 border-t border-gray-200 dark:border-gray-800 text-center text-xs text-gray-400 dark:text-gray-500">
        © {{ new Date().getFullYear() }} HelloPro — MCP Gateway
      </div>
    </div>
  </div>
</template>
