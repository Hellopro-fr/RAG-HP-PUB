# PENSE_IA.md — Workflow de pensée derrière le chantier

> Pour chaque pattern et chaque décision structurante : l'hypothèse de départ, les options envisagées, l'arbitrage, et **pourquoi** on a tranché ainsi.
> Utile pour : reprendre le chantier, expliquer un choix à un autre intervenant, éviter de remettre en cause des décisions sans nouveaux éléments.

---

## Partie 1 — Patterns de pensée généraux (méta-méthode)

### P1 — Cadrage exhaustif avant tout code

**Principe** : avant de produire la moindre ligne (YAML, doc, commande), poser **toutes** les questions de cadrage qui empêchent d'inventer.

**Pourquoi** : sur un chantier infra prod, une mauvaise hypothèse propagée silencieusement (ex: "le namespace existe déjà", "le service Milvus s'appelle X") génère des manifests qui semblent valides mais sont fonctionnellement faux. Coût de correction × 10 vs coût de la question préalable.

**Comment je l'applique** :
- Toute info non vérifiable dans le code → **placeholder explicite** + question batch en début de réponse
- Toute info vérifiable dans le code → grep/read d'abord, demander en confirmation seulement
- Limites : ne pas surcharger l'utilisateur de questions triviales (alignement convention, formats lisibles, etc.) — ces points : prendre une décision argumentée et la signaler comme arbitrable

**Exemple sur ce chantier** : avant `plan.md`, j'ai posé Q1-Q6 puis A1-A3 (10 points de cadrage). Sans ces réponses, j'aurais écrit un plan basé sur des hypothèses fausses (ex: cluster prod renommé, exposition externe par défaut, ingestion à notre charge…).

---

### P2 — Validation utilisateur entre chaque livrable

**Principe** : un seul livrable à la fois. Validation explicite avant d'enchaîner.

**Pourquoi** : la mémoire `feedback_execution_mode.md` du user dit explicitement "User exécute lui-même les commandes ops, je fournis + attends son retour". Étendu : produire 7 docs d'un coup gaspille du temps si la 1ʳᵉ porte une convention que l'utilisateur veut changer.

**Comment je l'applique** :
- Après chaque doc / chaque étape : pause + 2-4 questions de validation
- Pas de "je continue automatiquement"
- Inclure dans la pause les **points d'arbitrage** détectés en route (souvent les bonnes questions n'apparaissent qu'à l'écriture)

**Limite** : peut sembler verbeux. Compensation : poser uniquement des questions où la réponse change la suite.

---

### P3 — Matrice d'impact obligatoire pour toute action mutative

**Principe** : `🆕/✏️/❌ • Périmètre • Downtime • Réversible • Risque • Validation` sur chaque commande qui modifie l'état.

**Pourquoi** : c'est explicitement demandé par l'utilisateur (D15). Au-delà de la conformité, ça force à **se poser la question avant** de proposer une commande. Une commande sans réponse à "qu'est-ce qui se casse si ça plante ?" est une commande non maîtrisée.

**Comment je l'applique** :
- Lecture seule : 1 ligne `📖 Aucun impact prod`
- Mutation : matrice complète (6 axes)
- Bloc d'actions similaires (ex: 5 NetPol sur ns vide) : 1 matrice agrégée + nuances par action si pertinent

---

### P4 — Pré-check → dry-run → diff → apply → post-vérif

**Principe** : séquence safe par défaut sur toute action mutative.

**Pourquoi** : 4 filets de sécurité avant de toucher l'état réel.
- **Pré-check** détecte les contradictions (ressource existe déjà, ns non vide, placeholder non remplacé)
- **Dry-run server-side** valide la syntaxe + les permissions + les conflits côté API server (sans persister)
- **Diff** montre exactement ce qui va changer (créations vs modifications vs suppressions)
- **Apply** = action réelle
- **Post-vérif** confirme que l'état observé matche l'état attendu (pas juste "exit 0")

**Comment je l'applique** : systématique en S1. Pour les actions triviales (ex: `kubectl get`), le 📖 lecture seule suffit, pas de pré-check.

---

### P5 — Discovery (lecture seule) avant tout apply

**Principe** : récupérer les valeurs réelles du cluster (services, IPs, labels, namespaces) avant d'écrire / appliquer des manifests qui en dépendent.

**Pourquoi** : les noms Helm-générés (`milvus-prod-milvus`), les IPs internes VPC (`10.11.0.2`), les labels auto-K8s (`kubernetes.io/metadata.name`) ne sont pas devinables avec certitude. Une placeholder + discovery en début de sprint = source de vérité unique.

**Comment je l'applique** : section `§4 Discovery` au début de chaque sprint. Commandes en lecture seule, sans matrice d'impact, à dérouler avant les actions mutatives.

**Exemple** : sprint S1 §4 a découvert que le service Milvus s'appelle `milvus-prod` (pas `milvus-prod-milvus` que j'avais supposé) et que la VM GPU est en `us-east4` (pas `europe-west1` que j'avais supposé). Sans cette discovery → 2 manifests faux et un risque R7 manqué.

---

### P6 — Tracer toute dérive / dette technique plutôt que la passer sous silence

**Principe** : dès qu'un constat n'est pas conforme à l'état idéal (cluster nommé `-dev` pour la prod, drift code, NetPol non enforced), **ouvrir une DTxxx dans `debug.md`** avec owner + action future.

**Pourquoi** :
- Empêche le faux sentiment de propreté ("tout est OK")
- Donne au futur intervenant le contexte pour décider quoi traiter en priorité
- Crée un backlog de hardening explicite

**Limite** : ne pas transformer en "wishlist" infinie. Critère d'inclusion = constat **objectivement actionnable** + risque mesurable.

---

### P7 — Préférer la simplicité maîtrisée maintenant + hardening tracé pour plus tard

**Principe** : sur chaque arbitrage entre "solution parfaite mais complexe" et "solution simple mais améliorable", choisir la simple si :
- L'écart de risque est mesuré
- Le hardening est explicitement tracé (issue, sprint, owner)
- L'évolution future ne nécessite pas de récrire l'existant

**Pourquoi** : un chantier qui n'avance pas parce qu'on cherche la perfection technique = échec opérationnel. Mieux vaut livrer une infra prod simple + DT trackées qu'une infra "parfaite" jamais déployée.

**Exemples sur ce chantier** :
- NetPol `allow-internal-namespace` = `podSelector: {}` (tous pods se parlent intra-ns), hardening `tier=app/db` tracé en Q7 post-S6
- R8 NetPol non enforced → option (a) apply quand même (déclaratif), enforcement séparé hors S0-S8
- D17 pas de node pool dédié → cluster bridé à 60 % d'usage RAM suffit (51 GB libres)

---

## Partie 2 — Décisions structurantes (raisonnement court)

### D11 — NetworkPolicies scope ns `moteur-recherche` uniquement (option B)

**Hypothèse de départ** : aligner sur le pattern existant du repo `manifest/network-policies/` (default-deny + allow-X cluster-wide).

**Constat bloquant** : le pattern existant n'est **pas appliqué** sur le cluster (utilisateur). Donc s'aligner = soit (A) appliquer toutes ces NetPol cluster-wide (touche tous les ns existants, risque ÉLEVÉ de couper des flux non documentés), soit (B) scope au seul ns `moteur-recherche`.

**Arbitrage** : (B) — isolation du risque sans toucher à l'existant. Coût : sécurité du cluster reste inchangée hors notre ns. Ce n'est pas le scope de cette migration.

**Pourquoi pas (A)** : un chantier "appliquer la sécurité réseau cluster-wide" mérite son sprint dédié, sa pré-validation des flux applicatifs, son rollback plan. Pas à mélanger avec la migration d'un service.

---

### D16 — Re-ingestion catalogue Typesense **hors périmètre DevSecOps**

**Hypothèse initiale** : DevSecOps livre un Job K8s qui appelle l'endpoint `/ingest/products/from-milvus` après déploiement.

**Retournement** : retour utilisateur "ce sont les devs qui vont s'en charger". Notre rôle = livrer infra propre + fournir IP/endpoints/secrets aux devs.

**Conséquences** :
- Plus de Job d'ingestion à scripter (S2/S3 simplifiés)
- Plus d'endpoint applicatif à connaître (Q1 résolu — hors périmètre)
- L'app Typesense GKE peut démarrer **vide** (D16 = stratégie b "démarrage à vide")
- Frontière claire DevSecOps ↔ Lead Dev

**Pourquoi c'est un bon découpage** : l'ingestion = logique applicative (mapping schémas, gestion erreurs, retry) + connaissance métier des devs. Faire ça côté DevSecOps = sortir de notre périmètre + fragiliser la maintenance future.

---

### D18 — Exposition **interne** uniquement (Internal LB), pas d'Ingress externe

**Hypothèse initiale** : Ingress GKE + ManagedCertificate (TLS managé) + BackendConfig + Cloud Armor (WAF + IP allowlist).

**Découverte** (Q10) : `https://api.hellopro.eu/optimoteur-service` n'est pas un DNS direct sur notre service ; c'est une **API Gateway HelloPro** hébergée sur la VM GPU qui fait reverse-proxy vers notre service GKE.

**Conséquence** : notre service GKE n'a aucune raison d'être exposé sur Internet. La VM GPU (consommateur unique) accède au cluster via VPC interne (multi-région via global access LB).

**Arbitrage** : Service `Internal LoadBalancer` + annotation `internal-load-balancer-allow-global-access: true` + NetPol ingress allowlist `10.11.0.2/32`. **Pas** de TLS public, **pas** de Cloud Armor, **pas** de DNS public à gérer.

**Pourquoi c'est un gain** :
- Architecture 2× plus simple (pas de cert manager, pas de Cloud Armor à configurer)
- Surface d'attaque réduite à 0 internet
- Coût LB public économisé (~20 €/mois)
- Effort S4 : 1 j → 0,3 j

**Risque résiduel** : si un jour un autre consommateur doit appeler le service depuis internet, il faudra ajouter un Ingress externe → effort supplémentaire à ce moment-là, pas maintenant.

---

### D19 — Nouvelle API key Typesense forte (jamais réutiliser `hp_poc_2026`)

**Constat** : `hp_poc_2026` est codée en dur dans `docker-compose.yaml` + `credentials.py` du repo (commit Git public dans le mono-repo).

**Risque** : si réutilisée en prod, n'importe qui ayant accès au repo connaît la clé.

**Décision** : génération nouvelle clé prod (256 bits, base64), stockée en Secret K8s, valeur fournie au Lead Dev par canal sécurisé. La clé POC reste valable uniquement sur la VM GPU (POC) et n'a aucune valeur en prod.

**Pourquoi pas rotation continue** : Typesense ne supporte pas (encore) la rotation à chaud des API keys racine. Décision = clé statique forte, rotation = recreate StatefulSet (downtime). À automatiser plus tard si besoin (hors périmètre).

---

### D20 — Liveness `GET /` (light), Readiness `GET /health` (cascade Typesense)

**Constat code** : `main.py` expose `GET /` (juste `{"status":"ok"}`) ET `GET /health` (qui appelle `typesense_client.healthcheck()` en cascade).

**Erreur évitable** : utiliser `/health` pour la liveness = si Typesense flap, l'app sera restart en boucle → cascade de défaillance.

**Décision** :
- **Liveness** = `GET /` → vérifie juste que l'app Python répond. Si `/` échoue = vraiment cassée → restart justifié.
- **Readiness** = `GET /health` → si Typesense KO, l'app n'est pas "ready to serve" mais ne mérite pas restart. Le pod sera retiré du Service le temps que Typesense remonte.

**Référence pattern** : c'est la convention K8s standard pour les apps à dépendances externes. Liveness = "alive", Readiness = "ready".

---

### Choix migration parallèle (option c) sur R7 (VM GPU us-east4)

**Contexte** : VM GPU embedding hébergée en `us-east4` (cause root : pas de quota L4 GPU sur `europe-west1` au moment du provisionnement). Latence ~100 ms RTT vs cluster GKE EU. SLO `< 200 ms P95` à la limite.

**Options envisagées** :
- (a) Continuer migration en l'état + mesurer + accepter
- (b) Suspendre jusqu'à rapatriement EU
- (c) Migration parallèle : continuer (a) + sprint S8 dédié rapatriement post-migration

**Décision utilisateur** : (c). Cohérent avec :
- Le POC tourne déjà avec cette latence et fonctionne (preuve empirique)
- Le quota GPU EU est demandé en parallèle (chemin critique = obtenir le quota, pas la migration GKE)
- Découpage temporel sain : S0-S7 = migration GKE, S8 = rapatriement VM, indépendants

**Pourquoi pas (b)** : suspendre la migration GKE pour attendre un quota GCP = coupler 2 chantiers indépendants → risque de blocage long.

---

### R8 (NetPol non enforced) → option (a) apply quand même

**Contexte** : le cluster n'a ni Calico legacy, ni Dataplane V2. Les NetPol seront stockées dans etcd mais pas appliquées par le datapath.

**Tentation** : ne pas les appliquer ("ça sert à rien").

**Décision** : (a) les appliquer = traiter les NetPol comme du **code déclaratif** :
- Documentation explicite de l'intention sécurité
- Prêtes à enforcer dès activation (sprint hardening cluster séparé)
- Aucun risque (déclaratif + ns vide à ce stade)

**Pourquoi pas (b) "activer NetPol addon"** : touche le cluster entier, redémarre les CNI nodes, potentiel impact sur tous les workloads existants non documentés. Ce n'est pas le scope de cette migration.

---

## Partie 3 — Anti-patterns évités

| Anti-pattern | Pourquoi je l'évite | Détection |
|---|---|---|
| **Inventer un nom de Service / IP / port qu'on n'a pas vérifié** | Erreur silencieuse en prod, debug long | Question batch en début de sprint |
| **Bundler 7 docs en un seul tour** | L'utilisateur ne peut plus corriger une convention sans tout reprendre | Validation entre chaque livrable |
| **Apply direct sans dry-run** | Pas de filet sur les manifests neufs (typo, conflit, RBAC) | Pattern P4 systématique |
| **Cacher une dette technique pour que le rapport soit "tout vert"** | Bombe à retardement pour la suite | DTxxx ouverts dès détection |
| **Tout faire d'un coup pour aller vite** | Fatigue + erreurs cumulatives sur les data persistantes | Découpage S0-S8 + pause si nécessaire |
| **Sur-ingénier (ArgoCD, Istio, ExternalSecrets) sans besoin avéré** | Coût ops disproportionné vs valeur | "Cool tools syndrome" interdit |

---

## Partie 4 — À retenir si tu reprends ce chantier

1. **Lis `etat_avancement.md` en premier** — c'est le seul fichier toujours à jour
2. **Vérifie les hard facts** dans `CLAUDE.md` avant d'écrire un manifest
3. **Demande validation** avant chaque action mutative
4. **Note tout** : décisions dans `etat_avancement.md` (Dxx), incidents dans `debug.md` (#NNN), dettes dans `debug.md` (DTxxx)
5. **Ne supprime pas** une décision figée sans en discuter avec l'utilisateur
6. **Ne saute pas** la discovery au début de chaque sprint, même si "ça paraît évident"
7. **Si bloqué** : poser la question, ne pas contourner avec une hypothèse cachée
