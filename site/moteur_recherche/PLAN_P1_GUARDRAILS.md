# Plan d'implementation -- Garde-fous P1 Solr V2

> **Date de design** : 2026-05-18
> **Statut** : Specification validee, **a coder apres l'audit v4**
> **Auteur** : Decisions UX validees par rravelonarisoa@hellopro.fr

## Contexte

Sur la page 1 du moteur de recherche (`?ajax=1&core_v2=1`), c'est **Solr V2**
(`core0` text_fr + ASCIIFolding + FrenchLightStem) qui rend les 40 produits
en server-side. Probleme observe : quand la query est mal ecrite ou tres
specifique, Solr ramene quand meme 40 docs en bucket **LOW** (= aucun token
query dans le nom_produit) -> 40 produits hors-sujet affiches.

Le helper `hp_classify_and_alternate_docs` (`fonctions_annuaire_hp.php`)
classe deja les docs en HIGH/MID/LOW mais **garde tous les buckets** pour
maximiser le recall. On veut activer le **mode strict** pour P1.

## Decisions validees user

| Decision                          | Valeur                                                                  |
|-----------------------------------|-------------------------------------------------------------------------|
| Seuil HEALTHY (high_ratio min)    | **0.50** (au moins 50% des docs en HIGH)                                |
| Seuil HEALTHY (low_ratio max)     | **0.20** (max 8/40 produits sans aucun token)                           |
| Seuil TRASH (high max)            | **0** (aucun produit HIGH)                                              |
| Seuil TRASH (mid min)             | **3** (moins de 3 MID = query foireuse)                                 |
| Seuil TRASH (low_ratio alternatif)| **0.90** (90% LOW = bruit massif)                                       |
| Action TRASH                      | **Fallback Typesense AJAX 40 produits** (PAS "0 produit + did you mean") |
| Bandeau "Aucun match exact..."    | **NON** -- fallback transparent                                         |
| Timing                            | **Apres audit v4** (mesurer A3+A4 isoles d'abord)                       |

## Architecture cible (3 regimes)

```
Solr V2 -> 40 docs
            |
            v
hp_classify_and_alternate_docs (avec stats par bucket)
            |
            v
   hp_decide_p1_regime($stats)
            |
            +--> HEALTHY  : 40 Solr affiches, pas d'AJAX (UX actuelle)
            |
            +--> HYBRID   : N Solr (HIGH+MID) + (40-N) Typesense AJAX
            |               via search_extension.php?target_count=40-N
            |
            +--> TRASH    : 0 Solr + 40 Typesense AJAX
                            via search_extension.php?target_count=40
```

Note : TRASH = cas particulier de HYBRID avec `ext_target = 40`.
Cote code, on peut traiter en 2 branches (`healthy` vs `hybrid|trash`).

## UX par regime

### ✅ HEALTHY (ex: `compresseur`, `perceuse colonne`)
- 40 produits Solr rendus PHP server-side
- Aucun AJAX P1 (zero latence supplementaire)
- Pagination P2-P4 normale (prefetch Typesense)

### 🟡 HYBRID (ex: `melangeurs coniques`, `robot de nettoyage`)
- N produits Solr (HIGH + MID) rendus PHP en haut de liste
- (40-N) cards skeleton/loader animes en bas
- AJAX `search_extension.php?target_count=40-N` -> remplit les emplacements
- Pagination P2-P4 normale

### 🚨 TRASH (ex: `xyzqzqzq`, `asdfgh`)
- 0 produit Solr
- 40 cards skeleton animees pendant ~1-2s
- AJAX `search_extension.php?target_count=40` -> remplit toute la P1
- Pagination P2-P4 prefetch Typesense (offsets 40, 80, 120)

## Implementation -- fichiers a modifier

### 1. `site/annuaire_hp/fonctions/fonctions_annuaire_hp.php`

Modifier `hp_classify_and_alternate_docs` pour retourner aussi les stats :

```php
return [
    'docs'  => $reordered,
    'stats' => [
        'total' => count($docs),
        'high'  => $high_count,
        'mid'   => $mid_count,
        'low'   => $low_count,
    ],
];
```

Activer le mode strict via parametre `$exclude_low = false` (deja prevu dans
la signature mais non implemente -- cf signature documentee dans
`SESSION_2026-04-28_OPTIMISATION_RECHERCHE.md`).

### 2. `site/hellopro_fr/moteur_recherche.php`

Nouvelle fonction de decision :

```php
function hp_decide_p1_regime(array $stats): array {
    $total = $stats['total'];
    if ($total === 0) {
        return ['regime' => 'trash', 'display_count' => 0, 'ext_target' => 40];
    }

    $hr = $stats['high'] / $total;
    $lr = $stats['low']  / $total;

    // Regime TRASH
    if (($stats['high'] === 0 && $stats['mid'] < 3) || $lr >= 0.90) {
        return ['regime' => 'trash', 'display_count' => 0, 'ext_target' => 40];
    }

    // Regime HEALTHY
    if ($hr >= 0.50 && $lr < 0.20) {
        return ['regime' => 'healthy', 'display_count' => $total, 'ext_target' => 0];
    }

    // Regime HYBRID
    $kept = $stats['high'] + $stats['mid'];  // garde HIGH+MID, vire LOW
    return [
        'regime' => 'hybrid',
        'display_count' => $kept,
        'ext_target' => max(0, 40 - $kept),
    ];
}
```

Application dans le flow de rendu :

```php
$classified = hp_classify_and_alternate_docs(...);
$decision = hp_decide_p1_regime($classified['stats']);

// Filtre le tableau affiche selon le regime
if ($decision['regime'] === 'trash') {
    $tab_prod_rub = [];  // 0 Solr affiche, Typesense remplira via AJAX
} elseif ($decision['regime'] === 'hybrid') {
    // Vire les LOW
    $tab_prod_rub = array_filter($tab_prod_rub, fn($d) => $d['_bucket'] !== 'LOW');
}
// 'healthy' -> on garde tout
```

Injection dans HP_SEARCH_STATE :

```php
$state['regime'] = $decision['regime'];
$state['ext_target_count'] = $decision['ext_target'];
$state['solr_count'] = $decision['display_count'];
```

### 3. `site/design_system/js/moteur_recherche_ajax.js`

Modifier `loadExtension()` pour utiliser `STATE.ext_target_count` :

```javascript
function loadExtension() {
    if (!STATE.ext_target_count || STATE.ext_target_count === 0) {
        // Regime healthy : pas d'extension
        return Promise.resolve(null);
    }
    // ... rest of function
    params.set("target_count", String(STATE.ext_target_count));
    // ...
}
```

Bumper version JS `?v=20260518X` apres modif.

### 4. (Optionnel) `site/moteur_recherche/search_extension.php`

Verifier que le param `target_count` accepte jusqu'a **40** (pas seulement
les 20 historiques). Cap deja `min(40, $target_count)` actuellement -> OK.

## Tests utilisateur post-deploy

| Query                  | Regime attendu | Verification visuelle                                  |
|------------------------|----------------|--------------------------------------------------------|
| `compresseur`          | HEALTHY        | 40 Solr direct, pas de skeleton P1                     |
| `armoire medicale`     | HEALTHY ou HYBRID| Top 5 corrects, skeleton si peu de HIGH (verifier)   |
| `melangeurs coniques`  | HYBRID         | Quelques Solr HIGH + reste Typesense AJAX             |
| `xyzqzqzq`             | TRASH          | 40 cards Typesense apres skeleton ~1-2s               |
| `asdfgh` (typo)        | TRASH          | Idem                                                    |
| `perceuse 18V`         | HEALTHY        | 40 Solr direct                                          |

## Risques et mitigations

1. **Solr ramene peu de HIGH sur queries semantiques** : "voiture" peut ne pas
   matcher "Citroen C3" -> regime HYBRID involontaire. Mitigation : le helper
   `mascfem_variants_mt` + synonymes manuels font deja une bonne expansion.

2. **Typesense AJAX echoue (timeout/network)** : Solr P1 est vide (regime
   TRASH) -> rien a afficher. Mitigation : afficher un message "Erreur de
   chargement, reessayez". Eventuellement fallback sur les Solr LOW (mieux
   que rien) en cas d'echec critique.

3. **Performance** : 1 AJAX additionnel sur queries HYBRID/TRASH (~1s).
   Acceptable -- mieux qu'un mur de 40 produits hors-sujet.

## Estimation effort

- Fichiers modifies : 3 PHP + 1 JS
- Lignes de code : ~80 PHP + ~20 JS
- Tests cowork : ~30 min sur les 24 mots-cles audit + queries adversaires
- **Effort total : ~2-3h dont 1h test**

## Ordre d'execution recommande

1. Audit v4 (mesurer A3+A4 isoles)
2. Implementer P1 guardrails (cette PR)
3. Audit v5 (mesurer impact des guardrails sur les memes 24 mots-cles
   + queries trash adversaires)
4. Si OK -> attaquer R1 (regression "nettoyage") et R2 (marque Ritmo dur)

---

*Document genere le 2026-05-18 -- a maintenir si decisions UX changent.*
