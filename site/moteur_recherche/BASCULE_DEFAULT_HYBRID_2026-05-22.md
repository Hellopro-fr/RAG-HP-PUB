# Bascule par défaut : Solr V2 + Typesense hybride

**Date** : 2026-05-22
**Statut** : Spec — pré-déploiement GKE
**Fichier impacté** : `site/hellopro_fr/moteur_recherche.php` (PHP front Ecritel, non tracké git)
**PR (review-only)** : ce document
**Auteur** : Rija (rravelonarisoa@hellopro.fr)

---

## 1. Contexte

Depuis mai 2026, le pipeline `Solr V2 (page 1) + Typesense hybride (pages 2+ via
AJAX)` est en production sur le front HelloPro mais **uniquement opt-in** via les
paramètres URL `?ajax=1` ou `?hybrid=1`. Le défaut (aucun param) renvoie
toujours sur le RAG Milvus historique.

Validations à date qui justifient la bascule par défaut :

| Source | Résultat |
|---|---|
| Audit Cowork v3 (24 mots-clés Elena) | +10 % qualité BDD |
| Audit Hellopro v4 (24 mots-clés Elena) | +14 % qualité front |
| 4 plaintes commerciales Elena | 4/4 résolues (armoire medicale, soudure ritmo, ritmo, urinoir delabie) |
| Tests `e-crane`, `lockers bagagerie`, `sennebogen` | OK (synonymes manuels + IDF) |

→ Décision : passer le pipeline hybride en **comportement par défaut**, tout en
conservant un rollback simple et rapide.

---

## 2. Mécanisme du rollback

Le flag introduit dans `moteur_recherche.php` est `HP_USE_HYBRID_SEARCH`.

```php
if (!defined('HP_USE_HYBRID_SEARCH')) define('HP_USE_HYBRID_SEARCH', true);
```

Trois niveaux de rollback, du plus rapide au plus radical :

| # | Action | Délai | Audience |
|---|---|---|---|
| 1 | Ajouter `?legacy=1` à l'URL de test | 0 s | Debug ponctuel (Elena, Tech) |
| 2 | Passer `HP_USE_HYBRID_SEARCH` à `false` + redéployer le PHP front | ~5 min | Rollback global front |
| 3 | DevOps repointe la gateway `api.hellopro.eu/opti-moteur-recherche/` sur l'ancien backend | ~10 min | Urgence GKE down |

Note : les paramètres URL existants restent fonctionnels et non impactés :
- `?ajax=1` force le mode hybride (même comportement qu'avant)
- `?hybrid=1` force le mode hybride (même comportement qu'avant)
- `?is_solr=1` force Solr pur (BM25 strict, debug)
- `?typesense=1` force Typesense pur

---

## 3. Diff appliqué

### 3.1 Bloc flag (lignes 48-79)

```diff
+// ============================================================================
+// FLAG BASCULE PAR DEFAUT — Solr V2 + Typesense hybride (NEW 2026-05-22)
+// ----------------------------------------------------------------------------
+// HP_USE_HYBRID_SEARCH = true  : pipeline hybride par defaut (Solr P1 + Typesense P2)
+// HP_USE_HYBRID_SEARCH = false : retour au RAG Milvus historique
+//
+// Override ponctuel via URL :
+//   ?legacy=1  -> force le RAG Milvus historique (debug, A/B manuel)
+//   ?hybrid=1  -> force le pipeline hybride (deja existant, conserve)
+//   ?ajax=1    -> active aussi l'hybride (deja existant, conserve)
+//
+// Rollback rapide en production (par ordre de simplicite) :
+//   1. Editer cette ligne (false) et redeployer le PHP front Ecritel
+//   2. OU pointer la gateway api.hellopro.eu/opti-moteur-recherche/ sur l'ancien
+//      backend Milvus (DevOps, en cas d'urgence GKE down)
+// ============================================================================
+if (!defined('HP_USE_HYBRID_SEARCH')) define('HP_USE_HYBRID_SEARCH', true);
+
+$HP_LEGACY_FORCE = (isset($_GET['legacy']) && (string) $_GET['legacy'] === '1');
+
 $HYBRID_PAGE_MODE = (isset($_GET['hybrid']) && (string) $_GET['hybrid'] === '1')
-                  || $AJAX_PAGINATION_ENABLED;
+                  || $AJAX_PAGINATION_ENABLED
+                  || (HP_USE_HYBRID_SEARCH && !$HP_LEGACY_FORCE);
```

### 3.2 Bloc commentaire SELECTION MOTEUR (lignes 118-129)

```diff
 // SELECTION DU MOTEUR DE RECHERCHE (par ordre de priorite croissante) :
-//   1. Defaut (aucun parametre URL)        -> RAG (semantique Milvus)
-//   2. ?is_solr=1                          -> SOLR pur (BM25 strict)
-//   3. ?typesense=1 (ou canary X% trafic)  -> TYPESENSE (hybride API GCP)
-//   4. ?ajax=1 ou ?hybrid=1                -> HYBRIDE (Solr page 1 + Typesense AJAX page 1+2+3+4)
+//   1. Defaut depend de HP_USE_HYBRID_SEARCH (NEW 2026-05-22) :
+//      - HP_USE_HYBRID_SEARCH=true (defaut)  -> HYBRIDE (Solr V2 + Typesense)
+//      - HP_USE_HYBRID_SEARCH=false          -> RAG (semantique Milvus, legacy)
+//   2. ?legacy=1                             -> force RAG Milvus (debug)
+//   3. ?is_solr=1                            -> SOLR pur (BM25 strict)
+//   4. ?typesense=1 (ou canary X% trafic)    -> TYPESENSE (hybride API GCP)
+//   5. ?ajax=1 ou ?hybrid=1                  -> HYBRIDE (Solr P1 + Typesense AJAX P1ext+P2+P3+P4)
 // Chaque niveau OVERRIDE les niveaux precedents.

 $type = "RAG"; // 1. Defaut explicite : RAG semantique pour les queries floues B2B
+              //    (sera override en HYBRIDE plus bas si HP_USE_HYBRID_SEARCH actif)
```

---

## 4. Plan de bascule

| # | Étape | Owner | Pré-requis |
|---|---|---|---|
| 1 | Bench couverture toutes catégories (~150 mots-clés prod) | Rija | Génération CSV depuis `moteur_solr_historique` |
| 2 | Diff Milvus vs Typesense (recall@10, overlap, MRR) | Rija | Bench (1) terminé |
| 3 | Annotation Elena top-20 catégories sensibles | Elena | Diff (2) terminé |
| 4 | Migration VM → GKE (gateway upstream switch) | Tafita | Image Docker + `app/data/idf_nom_produit.json` + `.env` |
| 5 | Smoke test 24 mots-clés audit v4 sur GKE | Rija | (4) terminé |
| 6 | Merge ce PR + upload `moteur_recherche.php` sur Ecritel | Rija | (5) OK |
| 7 | Monitoring J+1 (taux erreur, latence p95, plaintes) | Rija + Tafita | (6) déployé |

---

## 5. Vérification post-déploiement

Tester ces 5 URLs après merge + upload :

```
# 1. Défaut (doit retourner HYBRIDE - regarder <!-- HP_QUALITY_P1 --> dans HTML)
https://www.hellopro.fr/moteur_recherche/recherche_resultat.php?type_recherche=produit&recherche_active=1&mot_cles=armoire+medicale

# 2. Force RAG Milvus (rollback URL)
https://www.hellopro.fr/moteur_recherche/recherche_resultat.php?type_recherche=produit&recherche_active=1&mot_cles=armoire+medicale&legacy=1

# 3. Force hybride explicite (must work as before)
https://www.hellopro.fr/moteur_recherche/recherche_resultat.php?type_recherche=produit&recherche_active=1&mot_cles=armoire+medicale&ajax=1

# 4. Force Solr pur
https://www.hellopro.fr/moteur_recherche/recherche_resultat.php?type_recherche=produit&recherche_active=1&mot_cles=armoire+medicale&is_solr=1

# 5. Page 2 (doit utiliser Typesense AJAX)
https://www.hellopro.fr/moteur_recherche/recherche_resultat.php?type_recherche=produit&recherche_active=1&mot_cles=armoire+medicale&page=2
```

Critère de succès : (1) et (3) renvoient le même HTML (à `mt_rand`, `id_session`
près). (2) renvoie le HTML legacy Milvus. (4) renvoie Solr seul.

---

## 6. Rollback procédure complète (urgence prod)

Si après bascule on détecte une régression > 10 % sur taux de clic ou plaintes
commerciales :

```bash
# Option A — édit PHP + redéploiement Ecritel (5 min)
ssh ecritel
sed -i "s/define('HP_USE_HYBRID_SEARCH', true)/define('HP_USE_HYBRID_SEARCH', false)/" \
    /var/www/.../hellopro_fr/moteur_recherche.php
# (puis reload PHP-FPM si OPcache actif)

# Option B — Tafita repointe la gateway
# api.hellopro.eu/opti-moteur-recherche/ -> ancien backend Milvus VM
```

Communiquer à Elena dans le canal #moteur-recherche pour confirmer le retour à
la normale.

---

## 7. Fichiers à mettre à jour après merge

| Fichier | Action |
|---|---|
| `site/hellopro_fr/moteur_recherche.php` (local) | ✅ Modifié (visible dans PR) |
| **Ecritel** `/var/www/.../hellopro_fr/moteur_recherche.php` | ⏳ À uploader après validation |
| `apps-microservices/opti-moteur-front/CLAUDE.md` | Ajouter section "Rollback Milvus" |
| `site/moteur_recherche/SESSION_2026-05-21_OPTIMISATIONS_AUDIT_BDD.md` | Ajouter Section 11 "Bascule défaut 2026-05-22" |

---

## 8. Liens

- Mémoire série mai 2026 : [`SESSION_2026-05-21_OPTIMISATIONS_AUDIT_BDD.md`](./SESSION_2026-05-21_OPTIMISATIONS_AUDIT_BDD.md)
- Architecture opti-moteur-front : [`../../apps-microservices/opti-moteur-front/CLAUDE.md`](../../apps-microservices/opti-moteur-front/CLAUDE.md)
- Précédent : Intégration Typesense canary [`../INTEGRATION_TYPESENSE_CANARY.md`](../INTEGRATION_TYPESENSE_CANARY.md)
