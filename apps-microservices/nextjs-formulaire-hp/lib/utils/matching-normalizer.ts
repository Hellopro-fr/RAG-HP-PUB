/**
 * Normalisation des données de matching vers le format Supplier pour l'affichage
 */

import type { Supplier, ProductSpec } from '@/types';
import type { CharacteristicsMap } from '@/types/characteristics';
import type { MatchingProduct, MatchingCharacteristic, ProductInfoItem } from '@/types/matching';
import type { ConsolidatedCharacteristic } from './equivalence-merger';

// =============================================================================
// CONSTANTS
// =============================================================================

const MATCHING_STATUS_LABELS: Record<number, string> = {
  1: 'Match',
  2: 'Écart',
  3: 'Bloquant', // Traité comme écart dans l'UI
  4: 'Non renseigné',
};

/** Image placeholder pour les produits sans image */
const PLACEHOLDER_IMAGE = '/images/product-placeholder.jpg';

/** Placeholder pour le nom du fournisseur */
const PLACEHOLDER_SUPPLIER = 'Fournisseur';

// =============================================================================
// HELPERS
// =============================================================================

/**
 * Récupère le label d'une caractéristique depuis la map
 */
function getCharacteristicLabel(
  characteristicsMap: CharacteristicsMap,
  idCaracteristique: number
): string {
  const char = characteristicsMap[idCaracteristique];
  return char?.nom || `Caractéristique ${idCaracteristique}`;
}

/**
 * Récupère les labels des valeurs pour une caractéristique
 * Gère les types numériques (valeur + unite) et textuels (id_valeur[])
 */
function getValueLabels(
  characteristicsMap: CharacteristicsMap,
  characteristic: MatchingCharacteristic
): string {
  const { id_caracteristique, type_caracteristique, valeur, unite, id_valeur } = characteristic;

  // Type numérique (1)
  if (type_caracteristique === 1) {
    if (valeur !== null) {
      const uniteStr = unite ? ` ${unite}` : '';
      return `${valeur}${uniteStr}`;
    }
    return '-';
  }

  // Type textuel (2)
  const char = characteristicsMap[id_caracteristique];
  if (!char || !char.valeurs || id_valeur.length === 0) {
    return '-';
  }

  const labels = id_valeur
    .map((idVal) => {
      const val = char.valeurs.find((v) => v.id === idVal);
      return val?.valeur;
    })
    .filter(Boolean);

  return labels.length > 0 ? labels.join(', ') : '-';
}

/**
 * Récupère la valeur cible attendue par l'utilisateur pour une caractéristique
 */
function getExpectedValue(
  characteristicsMap: CharacteristicsMap,
  equivalences: ConsolidatedCharacteristic[],
  idCaracteristique: number
): string | undefined {
  const userCriteria = equivalences.find(
    (eq) => eq.id_caracteristique === idCaracteristique
  );

  if (!userCriteria) return undefined;

  const char = characteristicsMap[idCaracteristique];

  if (userCriteria.type_caracteristique === 'textuelle') {
    // Valeurs cibles textuelles
    const cibles = userCriteria.valeurs_cibles;
    if (Array.isArray(cibles) && cibles.length > 0 && char?.valeurs) {
      const labels = cibles
        .map((id) => char.valeurs.find((v) => v.id === id)?.valeur)
        .filter(Boolean);
      return labels.join(', ');
    }
  } else {
    // Valeurs cibles numériques
    const cibles = userCriteria.valeurs_cibles;
    if (cibles && !Array.isArray(cibles)) {
      const unite = userCriteria.unite || char?.unite || '';
      if (cibles.exact !== undefined) {
        return `${cibles.exact}${unite}`;
      }
      if (cibles.min !== undefined && cibles.max !== undefined) {
        return `${cibles.min} - ${cibles.max}${unite}`;
      }
      if (cibles.min !== undefined) {
        return `>= ${cibles.min}${unite}`;
      }
      if (cibles.max !== undefined) {
        return `<= ${cibles.max}${unite}`;
      }
    }
  }

  return undefined;
}

/**
 * Construit les specs d'un produit à partir des critères utilisateur
 * Affiche TOUS les critères demandés, qu'ils soient présents ou non sur le produit
 */
function buildProductSpecs(
  matchingCharacteristics: MatchingCharacteristic[],
  characteristicsMap: CharacteristicsMap,
  equivalences: ConsolidatedCharacteristic[]
): ProductSpec[] {
  return equivalences.map((equivalence) => {
    // Chercher si le produit possède cette caractéristique
    const matchingChar = matchingCharacteristics.find(
      (mc) => mc.id_caracteristique === equivalence.id_caracteristique
    );

    const label = getCharacteristicLabel(characteristicsMap, equivalence.id_caracteristique);

    if (matchingChar) {
      // Si statut_matching === 4, traiter comme "non renseigné" même si présent
      if (matchingChar.statut_matching === 4) {
        const expected = getExpectedValue(characteristicsMap, equivalences, equivalence.id_caracteristique);
        return {
          label,
          value: '-',
          matches: false,
          expected,
          isRequested: true,
        };
      }

      // Caractéristique présente avec valeur renseignée
      // statut_matching === 1 → Match (corresponds)
      // statut_matching === 2 ou 3 → Écart/Bloquant
      const value = getValueLabels(characteristicsMap, matchingChar);
      const matches = matchingChar.statut_matching === 1;
      const expected = !matches
        ? getExpectedValue(characteristicsMap, equivalences, equivalence.id_caracteristique)
        : undefined;

      return {
        label,
        value,
        matches,
        expected,
        isRequested: true,
      };
    } else {
      // Caractéristique absente du produit → statut "non renseigné"
      const expected = getExpectedValue(characteristicsMap, equivalences, equivalence.id_caracteristique);

      return {
        label,
        value: '-',
        matches: false,
        expected,
        isRequested: true,
      };
    }
  });
}

/**
 * Construit les matchGaps (écarts de matching) pour un produit
 * Statuts 2 (écart) et 3 (bloquant) sont traités comme des écarts dans l'UI
 */
function buildMatchGaps(
  matchingCharacteristics: MatchingCharacteristic[],
  characteristicsMap: CharacteristicsMap,
  equivalences: ConsolidatedCharacteristic[]
): string[] {
  const gaps: string[] = [];

  for (const mc of matchingCharacteristics) {
    // Ignorer les matchs parfaits (statut 1)
    if (mc.statut_matching === 1) continue;

    const label = getCharacteristicLabel(characteristicsMap, mc.id_caracteristique);
    const value = getValueLabels(characteristicsMap, mc);
    const expected = getExpectedValue(characteristicsMap, equivalences, mc.id_caracteristique);

    if (mc.statut_matching === 4) {
      // Caractéristique non renseignée
      gaps.push(`${label} : non disponible`);
    } else if (mc.statut_matching === 2 || mc.statut_matching === 3) {
      // Écart (2) ou Bloquant (3) - traités de la même façon dans l'UI
      if (expected) {
        gaps.push(`${label} : ${value} (demandé ${expected})`);
      } else {
        gaps.push(`${label} : ${value}`);
      }
    }
  }

  return gaps;
}

/**
 * Normalise un produit de matching vers le format Supplier
 */
function normalizeProduct(
  product: MatchingProduct,
  characteristicsMap: CharacteristicsMap,
  equivalences: ConsolidatedCharacteristic[],
  isRecommended: boolean
): Supplier {
  const specs = buildProductSpecs(
    product.caracteristique,
    characteristicsMap,
    equivalences
  );

  const matchGaps = buildMatchGaps(
    product.caracteristique,
    characteristicsMap,
    equivalences
  );

  return {
    id: product.id_produit,
    // Placeholders - à enrichir avec l'API Produits
    productName: `Produit ${product.id_produit}`,
    supplierName: 'Fournisseur',
    rating: 0,
    distance: 0,
    // Score de matching (0-1 → 0-100)
    matchScore: Math.round(product.score * 100),
    // Images placeholder
    image: PLACEHOLDER_IMAGE,
    images: [PLACEHOLDER_IMAGE],
    // Passé en paramètre selon la liste (top_produit ou liste_produit)
    isRecommended,
    isCertified: false,
    // Specs et gaps calculés
    specs,
    matchGaps,
    // Description placeholder
    description: '',
    // Supplier placeholder
    supplier: {
      name: 'Fournisseur',
      description: '',
      location: '',
      responseTime: '',
    },
    // Champs de debug (non affichés dans l'UI)
    debugInfo: {
      coeff_geo: product.coeff_geo,
      coeff_type_frns: product.coeff_type_frns,
      characteristics_debug: product.caracteristique.map(c => ({
        id_caracteristique: c.id_caracteristique,
        bareme: c.bareme,
        poids_question: c.poids_question,
      })),
    },
  };
}

// =============================================================================
// MAIN EXPORT
// =============================================================================

export interface NormalizedMatchingResult {
  recommended: Supplier[];
  others: Supplier[];
}

/**
 * Normalise la réponse de l'API matching vers le format attendu par l'UI
 * L'API retourne désormais deux listes séparées : top_produit et liste_produit
 *
 * @param topProducts - top_produit de la réponse (recommandés)
 * @param otherProducts - liste_produit de la réponse (autres)
 * @param characteristicsMap - Map des caractéristiques (id → définition)
 * @param equivalences - Critères utilisateur consolidés (equivalenceCaracteristique du store)
 * @returns { recommended: Supplier[], others: Supplier[] }
 */
export function normalizeMatchingToSuppliers(
  topProducts: MatchingProduct[],
  otherProducts: MatchingProduct[],
  characteristicsMap: CharacteristicsMap,
  equivalences: ConsolidatedCharacteristic[]
): NormalizedMatchingResult {
  // Normaliser les produits recommandés
  const recommended = topProducts.map((product) =>
    normalizeProduct(product, characteristicsMap, equivalences, true)
  );

  // Normaliser les autres produits
  const others = otherProducts.map((product) =>
    normalizeProduct(product, characteristicsMap, equivalences, false)
  );

  // Trier par score décroissant
  recommended.sort((a, b) => b.matchScore - a.matchScore);
  others.sort((a, b) => b.matchScore - a.matchScore);

  return { recommended, others };
}

/**
 * Enrichit les Suppliers avec les informations produit de l'API get_info_produit
 *
 * @param suppliers - Liste de Suppliers à enrichir
 * @param productInfoMap - Map des infos produit (id → ProductInfoItem)
 * @returns Suppliers enrichis
 */
export function enrichSuppliersWithProductInfo(
  suppliers: Supplier[],
  productInfoMap: Record<string, ProductInfoItem>
): Supplier[] {
  return suppliers.map((supplier) => {
    const info = productInfoMap[supplier.id];
    if (!info) return supplier;

    const { produit, vendeur } = info;

    // Extraire le nom du fournisseur depuis le domaine
    const supplierName = vendeur.domaine
      ? vendeur.domaine.replace(/^www\./, '').split('.')[0].toUpperCase()
      : PLACEHOLDER_SUPPLIER;

    // Image du produit (peut être vide)
    const image = produit.image_produit || PLACEHOLDER_IMAGE;

    return {
      ...supplier,
      productName: produit.titre_produit || supplier.productName,
      supplierName,
      description: '', // On n'utilise pas la description HTML brute
      descriptionHtml: produit.description_produit || undefined,
      image,
      images: image !== PLACEHOLDER_IMAGE ? [image] : supplier.images,
      supplier: {
        ...supplier.supplier,
        name: supplierName,
        description: '',
      },
    };
  });
}
