# Plan — rendre une panne de détection visible

Spec : `docs/superpowers/specs/2026-08-14-crawler-detection-outage-visible-design.md`
(approuvée 2026-08-14, les deux volets).

Service : `apps-microservices/crawler-service/`. Quatre tâches. **1 → 2 → 3** touchent
`crawler/src/routes.ts` ou `main.ts` et doivent donc s'enchaîner ; la 4 est la doc.

## Outillage local

```bash
cd apps-microservices/crawler-service/crawler
npx tsc --noEmit
npx tsx --test src/class/DetectionLangueClient.test.ts src/unjudgedUrls.test.ts
```

`npm install --no-audit --no-fund` si `node_modules` est vide (**pas `npm ci`** — le
lockfile local n'est pas suivi et est désynchronisé, cf. le plan
`2026-08-14-crawler-detection-verdict-unavailable.md`).

**Mesurer la référence avant de coder, dans le même shell, et la citer dans le rapport.**
Elle bouge à chaque tâche livrée — ne jamais la reprendre de mémoire ni d'un autre plan.
Ni `routes.ts` ni `main.ts` n'ont de harnais dans ce service : leur vérification passe par
`tsc --noEmit` plus la lecture du diff, et ça doit être **dit** plutôt que maquillé par un
harnais factice.

**Règle de contrôle** : chaque test ajouté doit échouer dans **au moins une variante de
neutralisation**. Une seule direction ne prouve que les assertions pointant dans l'autre
sens — une constante `false` laisse passer trivialement tout test attendant `false`.

---

## Tâche 1 — Volet A, moitié Node : exit 10 sur la homepage

**Fichiers** `crawler/src/routes.ts`, `crawler/src/main.ts`.

Frontière vérifiée le 2026-08-14 : `const isMainSite = matchesMainSite(request.url, site)`
(`routes.ts:556`), `if (isMainSite) {` (`:578`), son `} else {` (`:771`). **Re-vérifier ces
ancres** avant d'éditer, elles bougent à chaque tâche de ce chantier.

Sur les **trois** sites homepage — `:644`, `:714`, `:767` — poser
`context.stopReason = "detectionUnavailable"` et `context.fatalExitCode = 10`, puis appeler
le `stopCrawler(...)` existant. Suivre le motif des branches voisines qui savent déjà
s'arrêter proprement : `:619-620` (challenge non résolu), `:649` et `:748` (échec d'écriture
de méthode).

**Ne toucher aucun des sept sites internes** (`:789`, `:814`, `:821`, `:833`, `:854`, `:889`,
`:898`) : tuer un crawl parce qu'une page interne n'a pas eu de verdict détruirait des
centaines de pages réussies. C'est le point où une lecture littérale de l'audit serait
nuisible.

Ajouter l'entrée `ERROR_MAP` (`main.ts:1126-1140`).

### Le cas MAJ — à trancher et à écrire, pas à subir

`context.homepageReady.resolve()` est délibérément **hors** du résultat de détection
(`routes.ts:1294-1295`), donc `seedPhase2` sème les URL du crawl précédent même sans verdict
de homepage. Un exit 10 supprimerait ce travail.

Lire ces deux sites, puis **choisir explicitement** entre « arrêter quand même » et « ne pas
arrêter en mode MAJ », et écrire la raison dans le code. La seconde est probablement la
bonne — les pages internes ont leur propre détection — mais elle suppose de distinguer une
panne *globale* d'un échec sur *cette* URL, information que le crawler n'a pas aujourd'hui.
Si tu ne peux pas trancher sur le code, **livrer le comportement initial-only** (gardé sur
`crawlMode`) et le dire, plutôt que de deviner.

---

## Tâche 2 — Volet A, moitié Python

**Fichier** `apps-microservices/crawler-service/app/core/crawler_manager.py`.

Dans `_classify_exit_code`, ajouter la branche 10 **avant** celle du 137, et ajouter `10` au
tuple d'exclusion :

```python
elif exit_code == 10:
    return ("Service de détection de langue indisponible", "detection_unavailable")
```

**Relire les numéros de ligne dans le fichier** : ceux de l'audit valent pour un état
antérieur du dépôt.

Vérifier ensuite que `is_success` exclut bien 10, sinon le statut resterait `finished` et la
tâche 1 serait inerte — c'est le seul contrôle qui prouve que la chaîne fonctionne de bout
en bout.

Rien à coordonner avec le BO : son auto-retrait est gardé par une allowlist de deux causes
(`proxy_blocked`, `domain_dead`), donc `detection_unavailable` ne retire rien (spec §2).

---

## Tâche 3 — Volet B : rendre la panne partielle comptable

**Fichiers** `crawler/src/routes.ts`, plus le `StatsManager`.

Un compteur — nom suggéré `verdict_unavailable` — incrémenté sur **les dix** sites, homepage
comprise. C'est la panne **partielle** qu'il rend visible : assez de pages jugées pour que le
dataset soit non vide et la couverture au-dessus de 80 %, le reste protégé en silence sur un
run étiqueté sain.

Deux contraintes non négociables :

- **Ne pas réutiliser `errors`.** Il alimentait la garde de santé du BO et les deux plafonds
  de suppression ; l'incrémenter ici rearmerait des freins qui bloquent *tout* le traitement
  destructeur. Décision hors périmètre (spec §7).
- **Vérifier la liste blanche du webhook** (`fonctions_scrapping.php:761-771`, dépôt
  Marketplace, **lecture seule**). Elle porte déjà `filtered_nonfr`. Un compteur absent de
  cette liste **n'arrive jamais au BO** : le correctif aurait l'air complet et serait inerte.
  Rapporter si une MEP BO d'une ligne est nécessaire — ne pas l'écrire dans cette tâche.

Décider aussi s'il faut poser un `crawlErrorMessage` pour les pages internes (aucun des sept
ne le fait aujourd'hui), en tenant compte de la troncature à 250 caractères et du fait que le
champ est **partagé** : écraser une cause plus grave serait une régression. Si le doute
subsiste, ne rien écrire et le dire.

---

## Tâche 4 — Documentation

`apps-microservices/crawler-service/CLAUDE.md` : la table des codes de sortie et le
vocabulaire `failure_cause` gagnent l'entrée 10 / `detection_unavailable` ; la section
`Detection Verdict Unavailable` gagne le compteur et la distinction homepage/interne.

**Et corriger ce que ces tâches rendent faux**, pas seulement ajouter — la règle du dépôt est
de réparer le `CLAUDE.md` dans le même commit que le code qui le contredit. Chercher en
particulier toute phrase affirmant qu'une panne de détection finit en succès, ou que ce
service n'ajoute aucun code de sortie.

## Déploiement

Rebuild `crawler-service`. Aucun changement de compose, aucune migration. Une MEP BO d'une
ligne **seulement si** la tâche 3 conclut que la liste blanche doit s'élargir, et elle part
**après** le rebuild.
