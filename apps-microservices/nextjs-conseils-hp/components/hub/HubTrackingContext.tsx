// ⚠️ Import depuis `hubPageContext` et NON depuis `hub.ts` : ce dernier porte
// `'use client'`, et un Server Component ne peut pas appeler une fonction d'un
// module client (échec constaté au build : « Attempted to call
// hubPageContextScript() from the server but hubPageContextScript is on the
// client »). Le module `hubPageContext` est neutre, importable des deux côtés.
import { hubPageContextScript } from '@/lib/analytics/hubPageContext';

/**
 * Pousse le contexte de page HUB (`hub_page_id`, `hub_page_uri`) dans le dataLayer.
 *
 * Server Component qui rend un `<script>` inline — délibérément, et non un
 * composant client avec `useEffect` : le script s'exécute au PARSING du document,
 * donc le contexte est disponible avant qu'un composant client puisse être
 * hydraté et pousser son premier événement. Avec un `useEffect`, l'ordre de
 * montage déciderait si `hub_page_id` accompagne l'événement ou non — un bug
 * intermittent, invisible en développement et détectable seulement dans les
 * rapports GA4 des semaines plus tard.
 *
 * Même motif que `GtmFooterScripts`, qui pousse `page_template` et le bloc `user`
 * de la même façon.
 *
 * ⚠️ À monter AVANT tout composant client émetteur d'événements dans l'arbre.
 * `HubTemplate` le place en tête de `<main>`.
 */
export function HubTrackingContext({ pageId, uri }: { pageId: number; uri: string }) {
  return <script dangerouslySetInnerHTML={{ __html: hubPageContextScript(pageId, uri) }} />;
}
