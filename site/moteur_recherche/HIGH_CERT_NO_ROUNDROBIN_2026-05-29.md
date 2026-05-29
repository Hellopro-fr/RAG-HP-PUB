# HIGH_cert sans round-robin — respect ordre Solr V2

**Date** : 2026-05-29
**Statut** : Spec — à uploader sur Ecritel
**Fichier impacté** : `site/annuaire_hp/fonctions/fonctions_annuaire_hp.php` (PHP front Ecritel, non tracké git)
**PR review-only** : ce document
**Auteur** : Rija

---

## 1. Symptôme observé

Sur `?v2=1&mot_cles=armoire+medicale` :
- Top 14 : tous des armoires médicales (corrects) ✅
- Pos 15-17 : produits non-pertinents (refrigerateur, armoire-vitrine, armoire-de-refroidissement) ❌
- Pos 28-29 : des armoires médicales pertinentes (`armoire-medicale-grande-hauteur`, `armoire-medicale-400`) que l'utilisateur attendait en top ❌

## 2. Diagnostic

Solr V2 fonctionne **parfaitement** : les 15 premiers docs Solr sont tous cert + tous tokens dans nom (boost cumul ^8000 actif). Vérifié via `debug_solr.php` (max score 64647, top 15 = 100% certifiés).

**Le problème vient de `hp_classify_and_alternate_docs`** qui :
1. Classifie les 200 docs Solr en HIGH/MID/LOW + cert/noncert
2. Applique un **round-robin par société avec cap 5** dans chaque bucket
3. Concat : HIGH_cert → HIGH_noncert → MID_cert → ...

Conséquence : si un fournisseur cert (ex: 2007191) a 15 vrais produits HIGH cert, **seuls les 5 premiers** restent dans le top initial. Les 10 autres sont déplacés en queue de file. Pendant ce temps, des produits MID cert ou HIGH noncert d'autres sociétés (peu pertinents) remontent.

## 3. Fix appliqué

**Pour le bucket HIGH_cert uniquement** : on ne fait PAS de round-robin, on respecte l'ordre Solr d'origine (= score décroissant).

Pour MID, LOW et HIGH_noncert : on conserve le round-robin (diversité sociétés).

### Diff appliqué

**Step 1 (ligne ~15148)** — ajouter `_solr_idx` au doc lors de la classification :

```diff
 $seen_ids = array();
+// 2026-05-29 : conserver l'ordre Solr d'origine pour HIGH_cert (cf Step 3).
+$solr_idx_counter = 0;

 foreach ($docs as $doc) {
     $pid = isset($doc[$f_id]) ? $doc[$f_id] : null;
     if ($pid === null) continue;
     if (isset($seen_ids[$pid])) continue;
     $seen_ids[$pid] = true;

     // ... classification HIGH/MID/LOW ...

+    // Tag l'index Solr d'origine sur le doc
+    $doc['_solr_idx'] = $solr_idx_counter;
+    $solr_idx_counter++;

     $sid = trim(...);
     if (!isset($buckets[$group][$cert_key][$sid])) { ... }
     $buckets[$group][$cert_key][$sid][] = $doc;
 }
```

**Step 3 (ligne ~15203)** — exception HIGH_cert :

```diff
 $result = array();
 foreach ($_groups_strict as $g) {
     foreach (array('cert', 'noncert') as $c) {
         if (count($result) >= $nb_max) break 2;
+
+        if ($g === 'HIGH' && $c === 'cert') {
+            // Flatten + trier par index Solr d'origine
+            $high_cert_flat = array();
+            foreach ($buckets[$g][$c] as $sid => $docs_societe) {
+                foreach ($docs_societe as $d) {
+                    $high_cert_flat[] = $d;
+                }
+            }
+            usort($high_cert_flat, function ($a, $b) {
+                $ai = isset($a['_solr_idx']) ? $a['_solr_idx'] : PHP_INT_MAX;
+                $bi = isset($b['_solr_idx']) ? $b['_solr_idx'] : PHP_INT_MAX;
+                return $ai - $bi;
+            });
+            foreach ($high_cert_flat as $d) {
+                if (count($result) >= $nb_max) break 3;
+                $did = $d[$f_id];
+                if (!isset($result[$did])) $result[$did] = $d;
+            }
+            continue;  // bucket HIGH_cert traite
+        }
+
+        // Comportement standard pour les autres buckets : round-robin societe
         $alt = $round_robin_capped($buckets[$g][$c], $societe_order[$g][$c], $cap_per_societe);
         foreach ($alt as $did => $d) { ... }
     }
 }
```

## 4. Effet attendu

| Pos | Avant (round-robin cap 5) | Après (ordre Solr) |
|---|---|---|
| 1-5 | 5 produits cert société A (ordre Solr) | 5 meilleurs produits cert (peut être tous société A) |
| 6-10 | 5 produits cert société B | Suite produits cert ordre Solr |
| ... | Mélange par cap | Tri pur par score Solr |
| 15+ | Produits non pertinents (MID cert d'autres soc) | Vrais produits HIGH cert restants |
| 28-29 | `armoire-medicale-grande-hauteur` (cert ignoré par cap) | Doit remonter en pos 6-10 |

## 5. Test post-deploy

```bash
# Comparer URL avant/après upload Ecritel
curl -sL "https://www.hellopro.fr/moteur_recherche/recherche_resultat.php?type_recherche=produit&recherche_active=1&mot_cles=armoire+medicale&v2=1" \
  | grep -oE 'href="https?://www\.hellopro\.fr/[^"]*-[0-9]+-[0-9]+-produit\.html"' \
  | head -20
```

**Critère succès** : `armoire-medicale-grande-hauteur` doit apparaître en pos 1-10 au lieu de 28.

Tester aussi avec autres queries Elena : `soudure ritmo`, `urinoir delabie`, `e-crane`, `melangeur conique`, `lockers bagagerie`.

## 6. Risque

⚠️ **Faible mais à surveiller** : un fournisseur cert avec 50 vrais produits HIGH (très rare) pourrait monopoliser tout le top. Le round-robin est conservé pour MID/LOW/HIGH_noncert ce qui assure la diversité après les ~15-20 premières positions.

Si problème observé : revert + ajuster.

## 7. Action après upload

1. Upload `site/annuaire_hp/fonctions/fonctions_annuaire_hp.php` sur Ecritel
2. Tester l'URL `?v2=1` ci-dessus
3. Si OK : présenter au DG
4. Si KO (cas inattendu) : revert (le code modifié n'a touché qu'une seule fonction, restore facile)

## 8. Liens

- Doc précédente toggle v2 : [`TOGGLE_V2_URL_AB_2026-05-28.md`](./TOGGLE_V2_URL_AB_2026-05-28.md)
- Mémoire complète : [`SESSION_2026-05-21_OPTIMISATIONS_AUDIT_BDD.md`](./SESSION_2026-05-21_OPTIMISATIONS_AUDIT_BDD.md)
