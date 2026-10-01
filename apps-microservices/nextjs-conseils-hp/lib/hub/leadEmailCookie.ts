'use client';

/**
 * Drapeau « ce navigateur a déjà soumis un lead POUR CE PROJET » — cookie 30 jours.
 *
 * ⚠️ La valeur stockée est UNIQUEMENT une liste d'`id_page_hub`, JAMAIS l'e-mail.
 * Un cookie est renvoyé au serveur à chaque requête du sous-domaine ; y mettre
 * l'e-mail l'exposerait inutilement (RGPD + poids). L'e-mail n'est transmis QUE
 * dans le corps de la soumission `POST /api/demande`, jamais persisté côté
 * navigateur.
 *
 * ⚠️ PORTÉE PAR PROJET, et c'est le cœur du sujet (corrigé le 2026-08-24). Le
 * drapeau valait auparavant `1`, sans notion de page : un visiteur converti sur
 * l'élevage obtenait ensuite le guide laverie SANS laisser son e-mail, donc
 * **sans qu'aucun lead laverie ne soit créé**. Or les leads sont rappelés en
 * fonction du projet consulté : ce visiteur n'aurait jamais été contacté sur son
 * projet de laverie. Chaque page HUB est un projet distinct, le drapeau doit
 * l'être aussi.
 *
 * Le coût pour le visiteur reste faible : l'API reconnaît son adresse et répond
 * 201 immédiatement, donc un seul champ e-mail, sans réclamer les coordonnées.
 *
 * Effet « visiteur reconnu SUR CETTE PAGE » :
 *  - `GuideDownloadDialog` : va directement à l'écran de téléchargement ;
 *  - `LeadPopup` : ne s'affiche pas au scroll (on ne redérange pas) ;
 *  - `AssistantForm` : PAS de raccourci (l'étape e-mail reste toujours affichée).
 */
const COOKIE_NAME = 'hub_lead';
const MAX_AGE_SECONDS = 30 * 24 * 60 * 60; // 30 jours

/**
 * Séparateur des ids dans la valeur du cookie.
 *
 * Ni `,` ni `;` — tous deux structurants dans un en-tête `Cookie` et donc
 * susceptibles d'être réécrits ou tronqués par un intermédiaire.
 */
const SEP = '.';

/**
 * Plafond du nombre d'ids conservés, les plus RÉCENTS d'abord.
 *
 * Il n'y a que trois pages HUB aujourd'hui, mais la valeur d'un cookie n'est pas
 * extensible à l'infini et rien n'empêche le catalogue de grandir. Au-delà, on
 * oublie les projets les plus anciens : le visiteur y sera simplement redemandé
 * son e-mail, ce qui recrée un lead — la dégradation va dans le bon sens.
 */
const MAX_IDS = 20;

/** Ids déjà convertis, lus depuis le cookie. */
function readIds(): string[] {
  if (typeof document === 'undefined') return [];
  const match = new RegExp(`(?:^|; )${COOKIE_NAME}=([^;]*)`).exec(document.cookie);
  if (!match) return [];
  return match[1]
    .split(SEP)
    .map((part) => part.trim())
    .filter((part) => /^\d+$/.test(part));
}

/**
 * true si ce navigateur a déjà soumis un lead POUR CE PROJET.
 *
 * ⚠️ Les cookies de l'ancien format valaient `1`. `1` n'étant l'id d'aucune page
 * HUB, ils sont lus comme « aucun projet converti » : les visiteurs concernés se
 * verront redemander leur e-mail une fois. C'est la dégradation souhaitée —
 * redemander une adresse coûte un champ, ne pas créer le lead coûte le contact.
 */
export function isLeadKnown(idPageHub: number): boolean {
  return readIds().includes(String(idPageHub));
}

/**
 * Marque ce projet comme converti et rafraîchit la fenêtre de 30 jours pour
 * l'ensemble de la liste.
 */
export function markLeadKnown(idPageHub: number): void {
  if (typeof document === 'undefined') return;
  const id = String(idPageHub);
  // Le plus récent en tête : c'est l'ordre qui décide qui saute au-delà du plafond.
  const ids = [id, ...readIds().filter((existing) => existing !== id)].slice(0, MAX_IDS);
  document.cookie = `${COOKIE_NAME}=${ids.join(SEP)}; path=/; max-age=${MAX_AGE_SECONDS}; samesite=lax`;
}
