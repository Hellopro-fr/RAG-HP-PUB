# Toggle A/B `?v2=1` — phase comparaison RAG Milvus vs Solr V2 + Typesense

**Date** : 2026-05-28
**Statut** : Spec — à uploader sur Ecritel après validation
**Fichier impacté** : `site/hellopro_fr/moteur_recherche.php` (PHP front Ecritel, non tracké git)
**Auteur** : Rija (rravelonarisoa@hellopro.fr)

---

## 1. Contexte

Suite à la livraison complète du nouveau moteur (Solr V2 + Typesense + IA),
on souhaite **comparer côte-à-côte** les 2 versions avant la bascule
définitive en production. Cela permet à Elena/Tech de qualifier les
différences sur les vraies requêtes utilisateurs.

**Décision** : revenir au RAG Milvus en défaut, et exposer un toggle URL
simple `?v2=1` pour activer le nouveau pipeline.

---

## 2. Mécanisme du toggle

### URLs de comparaison

| Moteur | URL exemple |
|---|---|
| **RAG Milvus** (défaut) | `https://www.hellopro.fr/moteur_recherche/recherche_resultat.php?type_recherche=produit&recherche_active=1&mot_cles={mot_cles}` |
| **Solr V2 + Typesense** | `https://www.hellopro.fr/moteur_recherche/recherche_resultat.php?type_recherche=produit&recherche_active=1&mot_cles={mot_cles}&v2=1` |

### Flag PHP

```php
// Defaut REVU 2026-05-28 : Milvus en defaut pour phase A/B
if (!defined('HP_USE_HYBRID_SEARCH')) define('HP_USE_HYBRID_SEARCH', false);

$HP_V2_FORCE     = (isset($_GET['v2']) && (string) $_GET['v2'] === '1');
$HP_LEGACY_FORCE = (isset($_GET['legacy']) && (string) $_GET['legacy'] === '1');

$HYBRID_PAGE_MODE = $HP_V2_FORCE
                  || (isset($_GET['hybrid']) && (string) $_GET['hybrid'] === '1')
                  || $AJAX_PAGINATION_ENABLED
                  || (HP_USE_HYBRID_SEARCH && !$HP_LEGACY_FORCE);
```

### Priorité (du plus prioritaire au moins prioritaire)

1. `?v2=1` (NEW) → force le mode hybride (URL officielle pour A/B)
2. `?hybrid=1` ou `?ajax=1` → forcent aussi le mode hybride (compat ascendante)
3. `HP_USE_HYBRID_SEARCH=true` (config PHP) → hybride par défaut sauf si `?legacy=1`
4. **Défaut** (rien) → RAG Milvus

---

## 3. Bascule définitive future

Quand on sera prêt à activer le hybride pour tous les utilisateurs :

```php
// Une seule ligne à modifier :
if (!defined('HP_USE_HYBRID_SEARCH')) define('HP_USE_HYBRID_SEARCH', true);
//                                                                    ^^^^
//                                                                    false -> true
```

Et `?legacy=1` permettra alors de retomber sur Milvus pour debug.

---

## 4. Diff appliqué (lignes 48-86 de `moteur_recherche.php`)

```diff
-// ============================================================================
-// FLAG BASCULE PAR DEFAUT — Solr V2 + Typesense hybride (NEW 2026-05-22)
-// ============================================================================
-if (!defined('HP_USE_HYBRID_SEARCH')) define('HP_USE_HYBRID_SEARCH', true);
-
-$HP_LEGACY_FORCE = (isset($_GET['legacy']) && (string) $_GET['legacy'] === '1');
-
-$HYBRID_PAGE_MODE = (isset($_GET['hybrid']) && (string) $_GET['hybrid'] === '1')
-                  || $AJAX_PAGINATION_ENABLED
-                  || (HP_USE_HYBRID_SEARCH && !$HP_LEGACY_FORCE);
+// ============================================================================
+// TOGGLE A/B MOTEUR DE RECHERCHE (REVU 2026-05-28)
+// Phase A/B : RAG Milvus en DEFAUT, ?v2=1 active le nouveau pipeline.
+// ============================================================================
+if (!defined('HP_USE_HYBRID_SEARCH')) define('HP_USE_HYBRID_SEARCH', false);
+
+$HP_V2_FORCE     = (isset($_GET['v2']) && (string) $_GET['v2'] === '1');
+$HP_LEGACY_FORCE = (isset($_GET['legacy']) && (string) $_GET['legacy'] === '1');
+
+$HYBRID_PAGE_MODE = $HP_V2_FORCE
+                  || (isset($_GET['hybrid']) && (string) $_GET['hybrid'] === '1')
+                  || $AJAX_PAGINATION_ENABLED
+                  || (HP_USE_HYBRID_SEARCH && !$HP_LEGACY_FORCE);
```

---

## 5. URLs de test (validation post-deploy Ecritel)

5 mots-clés à tester sur les 2 versions :

| Query | Lien RAG | Lien V2 |
|---|---|---|
| `armoire medicale` | `?mot_cles=armoire+medicale` | `?mot_cles=armoire+medicale&v2=1` |
| `soudure ritmo` | `?mot_cles=soudure+ritmo` | `?mot_cles=soudure+ritmo&v2=1` |
| `urinoir delabie` | `?mot_cles=urinoir+delabie` | `?mot_cles=urinoir+delabie&v2=1` |
| `e-crane` | `?mot_cles=e-crane` | `?mot_cles=e-crane&v2=1` |
| `lockers bagagerie` | `?mot_cles=lockers+bagagerie` | `?mot_cles=lockers+bagagerie&v2=1` |

Critère succès :
- URLs sans `?v2=1` → comportement Milvus (identique avant aujourd'hui)
- URLs avec `?v2=1` → comportement Solr V2 + Typesense (top-1 conforme cas Elena)

---

## 6. Action post-merge

1. Merger ce PR (review uniquement, fichier PHP non tracké)
2. Uploader `site/hellopro_fr/moteur_recherche.php` sur Ecritel
3. Tester les 5 URLs ci-dessus
4. Si tout OK : annoncer à Elena/Tech le toggle `?v2=1` pour leurs tests

---

## 7. Liens

- Doc précédente (bascule par défaut le 22/05) : [`BASCULE_DEFAULT_HYBRID_2026-05-22.md`](./BASCULE_DEFAULT_HYBRID_2026-05-22.md)
- Mémoire complète : [`SESSION_2026-05-21_OPTIMISATIONS_AUDIT_BDD.md`](./SESSION_2026-05-21_OPTIMISATIONS_AUDIT_BDD.md)
