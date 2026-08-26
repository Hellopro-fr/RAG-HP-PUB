/**
 * Contexte de page HUB — contrat PARTAGÉ serveur ↔ client.
 *
 * ⚠️ CE FICHIER N'A PAS `'use client'`, et c'est tout son intérêt.
 *
 * `lib/analytics/hub.ts` est un module client (il manipule `window`). Un Server
 * Component ne peut pas APPELER une fonction exportée par un module client — il
 * peut seulement en rendre un composant. `HubTrackingContext` est un Server
 * Component qui doit construire la chaîne du `<script>` : la fonction doit donc
 * vivre dans un module neutre, importable des deux côtés.
 *
 * Erreur produite si on la remet dans `hub.ts` (constatée au build Docker) :
 *   « Attempted to call hubPageContextScript() from the server but
 *     hubPageContextScript is on the client. »
 *
 * L'écriture (`hubPageContextScript`) et la forme lue par `getHubPageContext`
 * dans `hub.ts` doivent rester cohérentes : le type `HubPageContext` ci-dessous
 * est la source unique des deux côtés.
 */

export interface HubPageContext {
  hub_page_id: number;
  /**
   * URI PUBLIQUE canonique de la page, ex.
   * `/lancer-elevage-poules-pondeuses-1000-projet.html`.
   *
   * ⚠️ Ce n'est PAS la route interne. Un rewrite Next sert la page depuis
   * `/hub/<slug>-<id>` ; utiliser cette route-là remonterait dans GA4 une URL que
   * personne ne reconnaîtrait et qui ne recouperait ni `page_location`, ni la
   * Search Console, ni les logs serveur.
   *
   * Chemin sans nom d'hôte, délibérément : préfixer par l'origine ferait de
   * `localhost`, du domaine ngrok de recette et de la prod trois valeurs
   * distinctes pour une même page, et fragmenterait la dimension. Le nom d'hôte
   * est déjà porté par `page_location`.
   */
  hub_page_uri: string;
}

/**
 * Sérialise le push de contexte pour un `<script>` inline rendu côté serveur.
 * Exécuté au parsing du document, donc le contexte est dans le dataLayer avant
 * qu'un composant client hydraté puisse émettre son premier événement.
 */
export function hubPageContextScript(pageId: number, uri: string): string {
  const payload: HubPageContext = { hub_page_id: pageId, hub_page_uri: uri };
  // `JSON.stringify` n'échappe PAS `<` : une URI contenant `</script>` fermerait
  // la balise et le reste serait interprété comme du HTML. Elle vient de nos
  // fichiers de données, donc le risque est théorique — mais un JSON inline non
  // échappé est le motif d'injection le plus banal du web, et s'en protéger
  // coûte un `replace`.
  const json = JSON.stringify(payload).replace(/</g, '\\u003c');
  return `window.dataLayer=window.dataLayer||[];dataLayer.push(${json});`;
}
