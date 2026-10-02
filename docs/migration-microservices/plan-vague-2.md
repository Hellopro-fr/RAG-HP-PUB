# Plan de la vague 2 — qui fait quoi, comment, quand, où

> **Statut : proposition du 30/09, à valider en revue CTO + LEAD le jeudi 1/10.**
> La série des consumers (L1→L6) est close : 34 services tournent sur GKE. La vague 2 déplace ce qui reste de **public** sur la VM :
> les API HTTP, les MCP, la gateway, les fronts. Les services GPU, les bases et les backends gRPC **restent sur la VM**.
> Inventaire détaillé : [`inventaire-services-migration-par-lot.md`](inventaire-services-migration-par-lot.md) · préparation gateway : [`lots/L7.md`](lots/L7.md).
> **Suivi d'exécution (cases à cocher, journal Gandi, demandes Ecritel, décisions) : [`suivi-vague-2.md`](suivi-vague-2.md).**

---

## 1. En une page

**Ce qu'on bascule, c'est une adresse, pas un service.** Aujourd'hui, chaque adresse publique mène à la VM ; demain, elle mènera au cloud. Il y a quatre sortes d'« aiguillages », et chacun a son propriétaire :

| Aiguillage | Exemple | Qui le manœuvre | Où | Retour arrière |
|---|---|---|---|---|
| **Enregistrement DNS** d'un sous-domaine `*.hellopro.eu` | `rag.hellopro.eu` : IP VM → IP du load balancer | **DSO** | interface Gandi | remettre l'IP VM (effet en ≤ 5 min avec TTL 300 s) |
| **Route de la gateway** (fichier `.env.url`) | `SERVICE_SEARCH` : conteneur VM → URL Cloud Run | **DSO** | VM, `.env.url` monté dans `api-catalog` | remettre la ligne |
| **Ligne `mcp_servers`** en base `gateway_db` | URL d'un serveur MCP | **DSO** (dump avant) | MySQL VM | réimport de la ligne |
| **Règle Apache** du front `hellopro.fr` | `conseils.hellopro.fr` → back-end Next.js | **Ecritel** (si elle vise une IP) — sinon rien à faire chez Ecritel (voir § 5) | Apache Ecritel | règle d'origine |

**Le jumeau VM reste allumé** après la bascule d'un service sans état : c'est le repli le plus rapide. Il est **arrêté dans le même geste** seulement pour les services qui écrivent seuls au démarrage ou en boucle (`mcp-gateway`, `api-gateway-go`, `dlq-manager-service`).

**Ordre** : V2-0 prérequis (aucune bascule) → V2-a routes gateway → V2-b MCP → V2-c bloc gateway → V2-d fronts et SSO → V2-e stockage. Une adresse à la fois, en heures ouvrées, jamais le vendredi, décision J+1 à 9h30 — comme pour les lots.

---

## 2. Les rôles

| Rôle | Qui | Ce qu'on attend de lui dans la vague 2 |
|---|---|---|
| **DSO** | DevSecOps | Infra (load balancer, certificats, GKE, Cloud Run), DNS Gandi, routes gateway, bases, scripts, bascules, relevés, rollbacks, docs |
| **LEAD** | Lead Dev | Affecte les devs, valide les correctifs de code, valide fonctionnellement chaque bascule (GO J+1) |
| **Devs** | désignés par le LEAD par service | Remplacent les URL en dur, corrigent le code bloquant, testent le service basculé sur son parcours réel |
| **CTO** | Chef de projet IA | Valide le plan, arbitre le calendrier et les P9 |
| **PROD** | Chef de produit | Décide la bascule de `conseils` (SEO, pages PHP non migrées) |
| **RSSI** | (CTO) | Décide le passage de Cloud Armor en blocage réel |
| **Ecritel** | infogérance du front `hellopro.fr` | Répond à la question du § 5 ; modifie une règle Apache **seulement si** elle vise une IP |
| **Gandi** | registrar / DNS | Rien à demander : nous pilotons les zones nous-mêmes dans l'interface |

---

## 3. Sous-vague par sous-vague

Légende des lieux : **Gandi** = interface DNS · **TF** = Terraform `infra-microservices/` (branche `features/infra-gcp-prod`) · **VM** = `vm-embedding-g2-std-24-use` (`deploy` → `devhp`) · **K8s** = `kubectl` (config `kubectl-local`) · **GH** = GitHub (PR vers `prod`).

### V2-0 — Prérequis, aucune bascule · jeu 1/10 → ven 2/10

| # | Quoi | Qui | Comment | Où | Quand | Livrable / critère |
|---|---|---|---|---|---|---|
| 0.1 | Revue du plan, décisions du § 6 | CTO, LEAD, DSO, PROD | réunion 1 h | — | **jeu 1/10 matin** | plan validé, devs nommés par service |
| 0.2 | Mesures VM : volume horaire par adresse, que sert `dlq.hellopro.eu`, taille des volumes | DSO | commandes du § 7 (lecture seule) | VM | jeu 1/10 | chiffres dans ce document |
| 0.3 | **Load balancer HTTPS prod** (une IP publique fixe, un routage par nom d'hôte) avec les back-ends Cloud Run (`rag`, `login`, `nextjs-conseils`) | DSO | module TF `https_lb_cloud_run` (déjà éprouvé sur `crlb-demo.hellopro.eu`), `plan` relu puis `apply -target` | TF | jeu 1/10 | IP du LB ; chaque hôte répond via `curl --resolve <hôte>:443:<IP LB>` |
| 0.4 | **Certificats** des adresses de la vague, **émis avant** toute bascule DNS | DSO | Certificate Manager, validation par DNS : un enregistrement `CNAME _acme-challenge.<hôte>` par adresse | TF + **Gandi** | jeu 1/10 (émission : quelques minutes à quelques heures) | certificats `ACTIVE` |
| 0.5 | Entrée GKE pour `api.` et `mcp.` (le module actuel ne sait brancher que du Cloud Run) | DSO | NEG autonomes sur les Services K8s (`cloud.google.com/neg`) rattachés au même LB | K8s + TF | ven 2/10 | `curl --resolve api.hellopro.eu:443:<IP LB>` → gateway GKE (shadow) |
| 0.6 | **TTL à 300 s** sur toutes les adresses de la vague | DSO | modifier le TTL de chaque enregistrement A (valeur inchangée : `35.245.31.1`) | **Gandi** | **ven 2/10** (≥ 48 h avant la 1re bascule) | `dig +noall +answer <hôte>` montre 300 |
| 0.7 | Cloud Armor en **observation** sur le LB prod | DSO | politique existante en mode PREVIEW | TF | ven 2/10 | journaux de règles visibles |
| 0.8 | Liste des **URL en dur** `http://<conteneur>:<port>` par service (F-HP-DEV-005) | DSO (liste) → **devs** (correctifs) | recherche dans le code ; un ticket par service | GH | liste jeu 1/10 ; correctifs avant la bascule du service | PR mergées sur `prod` |
| 0.9 | **Test VM → Cloud Run** : la gateway VM peut-elle appeler un Cloud Run ? (entrée, authentification) | DSO | `curl` depuis la VM vers 2 services Cloud Run | VM | jeu 1/10 | OUI → V2-a comme prévu ; NON → V2-a passe après V2-c |
| 0.10 | Runbook de bascule HTTP et de rollback, scripts P1 / bascule / relevés | DSO | modèle des lots | GH (docs) | ven 2/10 | runbook mergé |
| 0.11 | Question à **Ecritel** (§ 5) | DSO envoie | message prêt | e-mail | **jeu 1/10** | réponse avant V2-d |

### V2-a — API HTTP internes (P4) · lun 5/10 → mar 6/10

Pas de DNS : on change **une route de la gateway VM à la fois**. Les utilisateurs continuent d'arriver sur `api.hellopro.eu` (VM) ; c'est l'appel suivant qui part vers le cloud.

| # | Quoi | Qui | Comment | Où | Quand | Critère |
|---|---|---|---|---|---|---|
| a.1 | P0 par service : URL en dur corrigées, secrets à parité, capacité Cloud Run calée sur la VM (`min instances ≥ 1`) | DSO ; devs pour les correctifs | fiche par service | code, SM, CR | veille de chaque service | fiche verte |
| a.2 | Bascule d'une route | DSO | ligne `SERVICE_<X>` de `.env.url` → URL Cloud Run, écriture **en place** (pas de `sed -i`, qui casse le montage) puis redémarrage d'`api-catalog` | VM | 1 route toutes les ~2 h, 9h30-16h | appels `2xx` dans les logs Cloud Run, 0 erreur nouvelle côté gateway |
| a.3 | Test fonctionnel du parcours | dev du service | parcours réel (recherche, classification…) | front / API | juste après a.2 | OK écrit dans le canal de bascule |
| a.4 | Relevés midi / 17h / nuit, décision J+1 | DSO, LEAD | scripts de relevé | CR, VM | J, J+1 9h30 | GO / rollback (remettre la ligne) |

Ordre proposé (du moins au plus sensible) : détection de langue, comparaison de texte, content-extractor, optimize, chat-llm, embedding HTTP, graph-rag recherche ×3, recherche, classification (10 réplicas VM), rest-milvus, ingestion, prix-traitement.

### V2-b — MCP (P5) · mer 7/10

| # | Quoi | Qui | Comment | Où | Quand | Critère |
|---|---|---|---|---|---|---|
| b.1 | Dump de `mcp_servers` | DSO | `mysqldump gateway_db mcp_servers` | VM | 9h | fichier daté conservé |
| b.2 | Une ligne `mcp_servers` à la fois → URL Cloud Run | DSO | `UPDATE … WHERE id=…` relu | MySQL VM | 1 serveur MCP / h | appel MCP réussi depuis un client réel |
| b.3 | Test d'un outil MCP par serveur | dev MCP | client MCP réel | — | après b.2 | OK écrit |
| b.4 | Clés tierces et quotas depuis l'IP de sortie `35.233.35.8` | DSO | vérification par fournisseur (Semrush, Ringover, Leexi, Google) | — | veille | pas de refus d'IP |

### V2-c — Bloc gateway B1 + B3 · une journée dédiée, semaine du 12/10

C'est le morceau le plus risqué : la gateway migre le schéma de sa base au démarrage et écrit des jetons. Tout se prépare en amont ; le jour J, on exécute.

| # | Quoi | Qui | Comment | Où | Quand | Critère |
|---|---|---|---|---|---|---|
| c.1 | Version du code gateway VM = image GKE ; parité des jetons (`ENCRYPTION_KEY`, `JWT_SECRET`, `GATEWAY_ADMIN_KEY`, `GOOGLE_TEMPLATES_RUNNER_ADMIN_TOKEN`, `ZOHO_GATEWAY_TOKEN`) | DSO ; **LEAD** confirme la version | empreintes VM = SM = K8s | VM, SM, K8s | semaine du 5/10 | tout identique |
| c.2 | Services K8s manquants, `.env.url` en ConfigMap, icônes MCP → stockage cible, sidecar nginx pour `/comparator` et `/crawler`, variables par défaut Docker posées | DSO | manifestes, `kubectl diff` puis `apply` | K8s + TF | semaine du 5/10 | `diff` relu, pods prêts en shadow |
| c.3 | **Dump complet de `gateway_db`** | DSO | `mysqldump` | VM | J 9h | fichier conservé, taille vérifiée |
| c.4 | Bascule mcp-gateway → mcp-zoho, templates-runner → api-gateway-go ; **jumeaux VM arrêtés dans le même geste** | DSO | scripts P3 (modèle des lots) | K8s, VM | J 9h30-11h | pods sains, 0 erreur de migration de schéma |
| c.5 | DNS `api.hellopro.eu` et `mcp.hellopro.eu` → IP du LB | DSO | changer la valeur de l'enregistrement A | **Gandi** | J 11h | `dig` → IP LB ; trafic nginx VM qui tombe |
| c.6 | `graph-rag-api-admin`, `graph-rag-dlq-manager` (routes gateway) | DSO | idem V2-a | K8s | J après-midi | appels `2xx` |
| c.7 | Tests fonctionnels gateway et MCP | devs désignés | parcours réels | — | J | OK écrits |
| c.8 | Rollback si besoin | DSO | A Gandi → `35.245.31.1`, `docker start` des jumeaux, dump si le schéma a divergé | Gandi, VM | à tout moment | retour ≤ 10 min |

### V2-d — SSO et fronts · semaine du 12/10, selon décisions

| # | Adresse | Qui | Comment | Où | Préalable |
|---|---|---|---|---|---|
| d.1 | `account-service-backend` (partage `gateway_db`) | DSO | Cloud Run, sortie en IP fixe (`all-traffic`) | CR | après V2-c |
| d.2 | `login.hellopro.eu` | DSO | A → IP LB | **Gandi** | d.1 ; clients OAuth enregistrés (**devs SSO**) |
| d.3 | `rag.hellopro.eu` | DSO | A → IP LB | **Gandi** | test de connexion par un dev |
| d.4 | `cmf.hellopro.eu`, front de `mcp.` | **devs** (création des fronts SSO) puis DSO | A → IP LB | Gandi | fronts construits et testés |
| d.5 | ~~`formulaire.hellopro.eu`~~ | — | — | — | ⏭️ **hors vague 2** (décision 3 du 30/09 : pas en production, fonctionnalités en cours) |
| d.6 | `conseils.hellopro.fr` | **PROD** décide, DSO exécute | A de **`nextjs-conseils.hellopro.eu`** → IP LB (voir § 5) ; Ecritel seulement si sa règle vise une IP | Gandi (± Ecritel) | GO PROD/SEO + réponse Ecritel |

### V2-e — Stockage images et crawler · après la vague 2

| # | Quoi | Qui | Comment | Où | Quand |
|---|---|---|---|---|---|
| e.1 | Cible GCS pour `image_download_data` (**370 Go** au 01/10 ; 237 Go au 20/07) et `crawler_data` (**205 Go** au 01/10 ; 374 Go au 20/07) | DSO propose, CTO valide | bucket + montage ou API GCS ; données reconstituables | TF | semaine du 19/10 |
| e.2 | Adaptation du code (`image-download` ×10, `image-cdn`, `crawler-service`) | devs | lecture / écriture GCS | code | à planifier |

---

## 4. Calendrier et mobilisation

> **Jeton Gandi (01/10)** : idéalement créé le **ven 2/10** ([procédure](procedure-jeton-gandi.md)) ; sinon le **lun 5/10 après-midi**. Dans ce second cas, seuls les CNAME de validation des certificats et le TTL 300 s glissent au 5/10 : **aucun effet sur V2-a et V2-b** (pas de DNS : routes de la gateway, lignes `mcp_servers`), ni sur V2-c / V2-d (semaine du 12/10, toujours plus de 48 h après le TTL).

| Date | DSO | LEAD / devs | CTO / PROD | Ecritel |
|---|---|---|---|---|
| **Jeu 1/10** | revue ; mesures VM ; LB + certificats ; test VM → CR ; message Ecritel ; liste des URL en dur par service | revue (plan validé) | revue ; décisions § 6 | reçoit la question |
| **Ven 2/10** | test d'entrée interne (0.19) ; Terraform LB + autorisations DNS des certificats (`plan`) ; NEG GKE ; runbook et script de bascule de route ; P0 des premiers services V2-a ; tickets d'URL en dur ; arrêt en réserve du service debug ; **si le jeton Gandi arrive** : CNAME de validation + TTL 300 s | titulaire Gandi : création du jeton ([procédure](procedure-jeton-gandi.md)) si possible | — | répond |
| **Lun 5/10 après-midi** (si jeton reporté) | jeton Gandi → CNAME de validation des certificats, **TTL 300 s** (≥ 48 h avant les bascules DNS de la semaine du 12/10) | — | — | — |
| **Lun 5 → mar 6/10** | V2-a (routes une à une) | tests fonctionnels à chaque route | — | — |
| **Mer 7/10** | V2-b (MCP) | tests MCP | — | — |
| **Jeu 8/10** | bilan ; préparation V2-c (c.1, c.2) | LEAD confirme la version gateway | point d'étape | — |
| **Sem. du 12/10** | V2-c (journée dédiée) ; V2-d | tests gateway, SSO, fronts | GO `conseils` | modification seulement si nécessaire |
| **Sem. du 19/10** | V2-e ; retrait IP publique VM quand plus rien n'y pointe | code GCS | — | retrait de `35.245.31.1` de leurs listes |

---

## 5. Demandes externes

### Gandi — rien à demander, tout se fait dans notre interface (DSO)

**Option recommandée : jeton d'accès personnel Gandi (API LiveDNS), temporaire et restreint**, plutôt que des clics dans l'interface. Chaque modification devient un script relu : lecture de la valeur actuelle (conservée pour le retour arrière), écriture, relecture, ligne dans le journal du suivi.

| Point | Règle |
|---|---|
| Création | par le titulaire du compte Gandi de l'organisation, dans l'interface Gandi (jetons d'accès personnels) |
| Périmètre | **domaine `hellopro.eu` seulement** (toutes les adresses de la vague, `nextjs-conseils` compris, sont en `.hellopro.eu` ; `hellopro.fr` n'est pas nécessaire) ; droit limité à la configuration technique / DNS — intitulé exact à vérifier à la création |
| Durée | expiration à la fin prévue de la vague (≈ 23/10), puis **révocation** |
| Stockage | Secret Manager `gandi-livedns-pat` (config `default`) ; jamais dans un fichier, un terminal partagé ou un message |
| Usage | API LiveDNS v5 (`https://api.gandi.net/v5/livedns/domains/hellopro.eu/records/<nom>/A`, en-tête `Authorization: Bearer`), scripts `GET` → `PUT` → `GET` exécutés par le DSO |

| Quand | Enregistrement | Action |
|---|---|---|
| jeu 1/10 | `_acme-challenge.<hôte>` (un par adresse de la vague) | **ajouter** le CNAME fourni par Certificate Manager (émission des certificats) |
| ven 2/10 | A de `api`, `mcp`, `rag`, `login`, `cmf`, `nextjs-conseils` (`.hellopro.eu`) | **TTL → 300 s**, valeur inchangée |
| jour de chaque bascule | A de l'adresse basculée | valeur `35.245.31.1` → **IP du LB** |
| rollback | idem | valeur → `35.245.31.1` |
| fin de vague | adresses basculées | TTL remonté (3600 s) |

### Ecritel — une seule question, message prêt à envoyer (jeu 1/10)

> **Objet : Règles Apache vers notre VM — conseils.hellopro.fr et www.hellopro.fr**
>
> Bonjour,
>
> Nous préparons la migration des services hébergés sur notre VM GCP (`35.245.31.1`) vers Google Cloud. Pour deux domaines servis par votre front Apache, pourriez-vous nous indiquer les règles qui envoient du trafic vers cette VM ?
>
> 1. `conseils.hellopro.fr` : quels chemins sont transmis, et vers quelle cible exactement — un **nom d'hôte** (par exemple `https://nextjs-conseils.hellopro.eu`) ou une **adresse IP** ? Avec ou sans `ProxyPreserveHost`, et avec vérification du certificat ?
> 2. `www.hellopro.fr` : même question pour les éventuels chemins transmis à la VM (formulaire).
> 3. Existe-t-il d'autres règles, sur d'autres domaines, qui visent `35.245.31.1` ?
>
> Une copie des blocs de configuration concernés nous suffit. Aucune modification n'est demandée à ce stade ; si une règle vise l'IP en dur, nous vous demanderons de la remplacer par un nom d'hôte lors de la bascule (date communiquée une semaine avant).
>
> Merci d'avance,
> L'équipe DevSecOps Hellopro

**Pourquoi cette question** : la VM porte un vhost `nextjs-conseils.hellopro.eu` (`nginx/nextks-conseils.conf`, vers `:8610`). Si Apache transmet `conseils.hellopro.fr` vers **ce nom d'hôte**, la bascule se fait **chez nous**, en changeant l'enregistrement A de `nextjs-conseils.hellopro.eu` dans Gandi : aucune intervention Ecritel le jour J. Si elle vise l'IP, Ecritel devra modifier la règle. Même logique pour `www.hellopro.fr`, que le vhost `formulaire` de la VM accepte aussi.

---

## 6. Décisions — pourquoi, objectif, options, recommandation

Chaque décision a un propriétaire et une échéance (tableau dans [`suivi-vague-2.md`](suivi-vague-2.md) § 5). Ce qui suit donne à chacun de quoi trancher en revue.

### Décision 1 — Plan, calendrier, un dev par service · CTO, LEAD · jeu 1/10

- **Pourquoi** : la vague 2 ne se fait pas sans les devs. Chaque route basculée (V2-a) et chaque serveur MCP (V2-b) doit être testé sur son parcours réel par quelqu'un qui connaît le service, et les URL en dur (F-HP-DEV-005) sont des correctifs de code.
- **Objectif** : que chacun sache, dès jeudi, quels jours il est mobilisé et sur quel service.
- **Options** : (A) le plan tel quel, point d'étape jeu 8/10 ; (B) ne valider que V2-0 et V2-a, et replanifier la suite après le bilan du 8/10.
- **Recommandation DSO** : **A**, avec le point d'étape du 8/10 comme porte de sortie. Il faut un nom par service P4/P5 (14 routes, 8 MCP) ; un même dev peut en couvrir plusieurs.
- **Décision (01/10)** : ✅ **plan validé ; devs disponibles à partir du lun 5/10.** Conséquence : les correctifs d'URL en dur démarrent le 5/10 ; V2-a commence par les routes **sans** URL en dur (liste DSO du 1-2/10), les autres suivent leur correctif.
- **Si on ne tranche pas** : V2-a ne peut pas démarrer le 5/10 (pas de testeur, pas de correctif d'URL).

### Décision 2 — `conseils.hellopro.fr` · PROD, LEAD · avant V2-d

- **Pourquoi** : `nextjs-conseils-hp` remplace **progressivement** des pages PHP. Le front Apache d'Ecritel décide quels chemins vont à Next.js ; le reste reste en PHP. Basculer tout le sous-domaine casserait les pages non migrées — ce n'est **pas** ce qu'on propose.
- **Ce qu'on bascule réellement** : seulement le **back-end** Next.js, en changeant l'adresse de `nextjs-conseils.hellopro.eu` (si Ecritel proxifie par ce nom — question du § 5). Les chemins servis par Next.js ne changent pas ; le SEO n'est pas touché si le contenu est identique.
- **Objectif** : sortir ce front de la VM sans changement visible pour les visiteurs ni pour les moteurs de recherche.
- **Risques à couvrir** : la version Cloud Run est reconstruite depuis `prod` (Next 15.5.24, correctif de sécurité F-HP-SEC-019) — elle peut différer de la VM ; démarrage à froid si le service descend à zéro instance.
- **Options** : (A) basculer le back-end en V2-d, `min instances = 1`, après comparaison de pages par PROD ; (B) attendre la fin de la refonte progressive.
- **Recommandation DSO** : **A**. Avant la bascule, PROD compare un échantillon de pages servies par Cloud Run (`curl --resolve`, sans rien changer pour le public) avec les mêmes pages servies par la VM.
- **Décision (30/09)** : ✅ **GO A** — on compare et on vérifie d'abord ; **les contenus ne doivent pas différer** (condition de bascule).
- **Si on ne tranche pas** : `conseils` reste sur la VM, qui ne peut pas être libérée de ses entrées publiques.

### Décision 3 — Formulaire Next.js · LEAD · ✅ prise le 30/09

- **Décision** : **hors vague 2.** `nextjs-formulaire-hp` n'est pas déployé en production (fonctionnalités en cours de développement) ; la migration Next 15 n'est pas urgente.
- **Conséquences** : `formulaire.hellopro.eu` reste sur la VM et n'est pas inclus dans les TTL ni les certificats de V2-0 ; action d.5 reportée. Le Cloud Run `nextjs-formulaire-hp` reste en shadow. À reprendre quand le LEAD annonce une mise en production — il faudra alors vérifier la règle Ecritel sur `www.hellopro.fr` (le vhost VM `formulaire` accepte aussi ce nom).

### Décision 4 — Services P9 à trancher · LEAD · jeu 8/10

- **Pourquoi** : ces services n'ont ni cible ni avenir décidés. Tant qu'ils existent, la VM ne peut pas être libérée, et deux routes de la gateway pointent encore vers des cibles floues (dont une IP en dur).
- **Objectif** : pour chacun, une réponse parmi **migrer / garder sur la VM / supprimer**.

| Service | Ce qu'on sait | Proposition DSO |
|---|---|---|
| `api-gateway-service` (Python) | ancienne gateway, remplacée par `api-gateway-go-service` ; déclare le même port 8500, ne répond plus ; gardée « pour le rollback » | supprimer après V2-c (le repli est alors le jumeau Go) |
| `api-model-service` | usage non documenté | le LEAD confirme l'usage ; sinon suppression |
| `api-chatbot-service` | profil `disabled` | supprimer si aucun projet de réactivation |
| `graph-rag-api-recherche-service-debug` | profil `disabled`, mais **1 318 lignes de logs en 7 jours** : quelque chose le lance | identifier l'appelant, puis supprimer |
| route `SERVICE_CRAWLING` | cible non décidée (`reverse-proxy:8050/crawler`) | à trancher avec V2-e (crawler) |
| route `SERVICE_OPTIMOTEUR` | **IP en dur** | donner un nom stable avant V2-c |

- **Si on ne tranche pas** : ces services restent sur la VM par défaut ; la ConfigMap `.env.url` de V2-c reprend les routes telles quelles.
- **Décision (01/10)** : ✅ **règle générale** — tout service qui n'est pas migré vers Cloud Run / GKE **reste sur la VM pendant un temps** : **UP** s'il est encore utilisé et ne peut pas être migré, **arrêté (conservé en réserve)** s'il n'est plus utilisé. L'action 0.13 (usage réel sur la VM) classe chaque service dans l'un des deux cas ; aucune suppression pendant la vague.

### Décision 5 — `dlq-manager-service` et `dlq.hellopro.eu` · métier, CTO · ⚠️ faits corrigés le 30/09

- **Fait nouveau (30/09)** : le service **tourne** sur la VM (`Up 2 months (healthy)`, port `8585`) — contrairement à la fiche L7 qui le croyait désactivé. Sa boucle d'auto-archivage s'applique donc déjà à l'Elasticsearch prod, et **`dlq.hellopro.eu` l'expose sur internet sans aucune authentification** (nginx sans contrôle d'accès, code sans authentification, CORS `*`) → **F-HP-SEC-028, CRITICAL**.
- **Mesure immédiate (sans attendre la décision)** : lire le journal d'accès nginx de `dlq.hellopro.eu`, puis fermer l'accès public au niveau nginx (authentification HTTP ou liste d'IP). Réversible en une commande.
- **Décision qui reste à prendre** : qui utilise cet outil, et doit-il migrer en vague 2 ? (A) garder, migrer sur GKE en V2-c derrière authentification (SSO ou jeton) et règle réseau, jumeau VM arrêté dans le même geste (sinon deux boucles d'auto-archivage) ; (B) retirer l'outil et l'adresse.
- **Recommandation DSO** : A si l'outil est utilisé (le journal d'accès le dira), avec correction de F-HP-SEC-027 avant toute exposition.
- **Décision (01/10)** : ✅ **on laisse sur la VM d'abord** — UP, restreint aux IP Hellopro (F-HP-SEC-028 atténué) ; migration sur GKE plus tard, **seulement** quand F-HP-SEC-027 (authentification) est corrigé.

### Décision 6 — Cloud Armor : quand bloquer · RSSI · avant V2-d

- **Pourquoi** : le load balancer rend les services joignables depuis internet. Cloud Armor filtre les attaques courantes (injections, scans, abus) ; en mode observation, il **journalise** sans bloquer.
- **Objectif** : bloquer le trafic malveillant **sans** bloquer les appels légitimes (back-office PHP, partenaires, les 6 IP legacy qui appellent certains ports en direct).
- **Options** : (A) observation pendant la vague, puis blocage **adresse par adresse** après 7 jours sans faux positif ; (B) blocage immédiat.
- **Recommandation DSO** : **A**, plus une limite de débit sur `login.hellopro.eu` dès sa bascule.
- **Si on ne tranche pas** : les services restent protégés seulement par leur propre authentification.

### Décision 7 — CD GKE prod (F-HP-IND-005) · CTO · jeu 1/10

- **Pourquoi** : sur les 34 consumers basculés, 2 seulement ont un déploiement automatique. Pour les autres, une livraison des devs passe par un déploiement manuel du DSO — l'équipe reste bloquée sur ses features si on tarde.
- **Objectif** : que les devs livrent sur les services basculés par une PR vers `prod`, avec la gate et une approbation, sans intervention manuelle.
- **Options** : (A) en parallèle de la vague 2 ; (B) juste après (semaine du 19/10).
- **Recommandation DSO** : **cadrage cette semaine (1-2/10), branchement semaine du 19/10** : la vague 2 mobilise déjà le DSO à plein les semaines du 5 et du 12/10. Prérequis : rightsizing mémoire, environnement `production` avec relecteur, retrait des jumeaux VM consumers.
- **Décision (30/09)** : ✅ GO, **de façon progressive** : un service branché par jour, testé et validé avant le suivant.
- **Si on ne tranche pas** : les livraisons des devs sur ces services restent manuelles.

### Décision 8 — Certificats par validation DNS · CTO, DSO · jeu 1/10

- **Pourquoi** : le certificat « managé » actuel du module ne s'émet **qu'une fois le DNS basculé** vers le load balancer. Entre la bascule et l'émission (quelques minutes à quelques heures), les visiteurs verraient une **erreur de certificat**.
- **Objectif** : aucune coupure TLS au moment de la bascule.
- **Options** : (A) Certificate Manager avec validation DNS : un CNAME `_acme-challenge` par adresse chez Gandi, certificat émis **avant** la bascule ; (B) garder le module actuel et accepter la fenêtre d'erreur.
- **Recommandation DSO** : **A**. Coût : une évolution du module Terraform et un CNAME par adresse.
- **Si on ne tranche pas** : B, avec une fenêtre d'erreur à chaque bascule.

### Décision 9 — Jeton API Gandi temporaire · CTO, DSO · jeu 1/10

- **Pourquoi** : une modification DNS à la main (interface) est rapide mais sans trace ni relecture ; une erreur de saisie coupe une adresse publique.
- **Objectif** : chaque modification DNS devient un script relu qui garde la valeur d'origine, écrit, relit, et laisse une ligne dans le journal Gandi du suivi.
- **Risque** : un jeton volé permet de modifier la zone. **Parades** : `hellopro.eu` seul, droit DNS seul, expiration vers le 23/10, rangé dans Secret Manager, révoqué en fin de vague.
- **Options** : (A) jeton temporaire + scripts ; (B) interface Gandi + journal rempli à la main.
- **Recommandation DSO** : **A**.
- **Si on ne tranche pas** : B.

---

## 7. Mesures VM (DSO, lecture seule, jeu 1/10)

```bash
# que sert dlq.hellopro.eu ? (dlq-manager-service est en profil disabled)
docker ps --filter publish=8585 --format '{{.Names}}\t{{.Status}}'; curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8585/
# volume horaire des requêtes nginx (répéter sur le fichier de chaque vhost s'il est séparé)
sudo awk '{print substr($4,2,14)}' /var/log/nginx/access.log | sort | uniq -c | tail -48
# taille actuelle des volumes nommés
docker system df -v | grep -E 'image_download_data|crawler_data'
```

---

## 7ter. Exposition des Cloud Run — cible validée le 02/10

Audit du 01/10 : 29 Cloud Run sur 31 étaient publics et anonymes (wrappers CD en `ingress: all` + `allow_unauthenticated: true`) — `allUsers` retiré partout le 01/10 (F-HP-SEC-030). Test du 02/10 sur un service sans trafic : en entrée **`internal-and-cloud-load-balancing`**, **internet reçoit 404, la VM et les pods GKE obtiennent 200**.

| Catégorie | Cible | Posée quand |
|---|---|---|
| API et MCP appelés par la gateway, les MCP ou les consumers | entrée `internal-and-cloud-load-balancing` + appel anonyme (`allow_unauthenticated: true`) + `min_instances: 1` | dans le wrapper CD, **au moment de la bascule de sa route** (V2-a, V2-b) |
| Fronts publics (`rag.`, `login.`, conseils…) | même entrée : le public passe **par le load balancer** (Cloud Armor), l'URL `run.app` reste fermée | à la bascule DNS (V2-d) |
| Services non basculés | restent sans `allUsers` (aucun appelant) | déjà fait (01/10) |

**Parité de code (02/10)** : la VM fait tourner le code de `features/poc` (branche des devs) ; Cloud Run est construit depuis `prod`. Sur les 4 premiers services, 2 font tourner sur la VM un fichier **absent de `prod`** (un correctif de production du 24/09 pour detection-langue). Règle : **avant de basculer une route, le code du service (et de ses bibliothèques) est remonté de `poc` vers `prod` par les devs, dans une PR qui porte aussi les réglages cible du wrapper** (entrée interne, appel anonyme, `min_instances: 1`, variables manquantes) ; le merge redéploie Cloud Run avec le bon code et la bonne exposition. Contrôle : `p0_code.sh` (VM = image Cloud Run).

**Prérequis** : le smoke test du workflow réutilisable `deploy-cloud-run.yml` ne s'ignore aujourd'hui que pour `ingress: internal` ; avec `internal-and-cloud-load-balancing`, le runner GitHub (internet) échouerait et déclencherait le retour arrière automatique. Le corriger (ignorer toute entrée ≠ `all`) **avant** de modifier le moindre wrapper.

## 7quater. Rapatriement `features/poc` → `prod` (constat du 02/10)

Des **correctifs urgents** partent sur la VM par `features/poc` ; ils ne sont pas dans `prod`, d'où sont construites les images Cloud Run et GKE. Base commune des deux branches : `fe7a6923` (25/08). Services touchés depuis par des commits présents **seulement** dans `poc` (relevé du 02/10) :

| Service / bibliothèque | Dernier commit `poc` seul | Sous-vague | À faire |
|---|---|---|---|
| `api-detection-langue-fr` | 24/09 (fuite du pool de navigateurs, correctif PROD) | V2-a | rapatrier **avant** la bascule (DSO) |
| `content-extractor-api-service` + `libs/common-utils` (`HeaderFooterExtractor`, `cache_service`) | 30/09 | V2-a | rapatrier **avant** la bascule |
| `mcp-semrush-service` | 02/09 | V2-b | à vérifier en P0 |
| `mcp-gateway-service`, `mcp-template-neo4j-service`, `mcp-gateway-frontend` | 30/09 | V2-c / V2-d | à rapatrier avec le bloc gateway |
| `nextjs-conseils-hp`, `crawler-monitor-*` | 18/09, 28/08 | V2-d | idem |
| `crawler-service`, `image-download-service` | 02-03/09 | V2-e | idem |
| `agent-service`, `graph-rag-normalize-unite-service` | 01-02/10 | hors vague (nouveau / reste sur la VM) | — |

**Consumers L1→L6 (déjà sur GKE)** : aucun commit `poc` seul sur leur code ; seul point d'attention, `website-processor-service` importe des modules de `common_utils` modifiés le 30/09 dans `poc`.

**Règles**
1. Avant chaque bascule : `p0_code.sh` (le code VM = l'image Cloud Run ?) et `p0_diff.sh` (origine `poc` / `prod`).
2. Rapatriement **assuré par le DSO** (décision du 02/10, pour garantir que tout est fait) : PR `poc` → `prod` du **code fonctionnel uniquement** : on garde les `requirements.txt` épinglés et les Dockerfile de `prod` (durcissement CD3.c, gate Trivy). La même PR porte les réglages cible du wrapper.
3. **Après la bascule d'un service, ses correctifs vont dans `prod`** (PR, gate, CD) et plus par `poc` → VM : la VM ne le sert plus. Jusqu'au CD GKE (F-HP-IND-005), le DSO redéploie les services GKE à la main.

## 7bis. Dépendances entre ce qui reste sur la VM et ce qui migre

**Règle (01/10)** : un jumeau VM n'est arrêté que lorsque **plus aucun service resté sur la VM ne l'appelle** — ou que ces appelants ont été repointés vers la nouvelle adresse (URL Cloud Run, IP interne d'un Service GKE, enabler `10.11.0.2`). À chaque bascule, le P0 liste les appelants restés sur la VM ; la bascule de l'entrée et l'arrêt du jumeau peuvent donc être décalés.

**Chemins réseau disponibles** :

| Sens | Chemin | Déjà utilisé |
|---|---|---|
| Cloud (GKE / Cloud Run) → VM | enabler haproxy `10.11.0.2:150xx` (gRPC, tracking `:8590`) | oui, depuis L1 |
| VM → GKE | IP interne d'un Service GKE de type load balancer interne (`10.0.1.x`) | oui : `SERVICE_OPTIMOTEUR=http://10.0.1.240:8570` dans `.env.url` |
| VM → Cloud Run | URL `https://…run.app` (entrée et authentification à valider : action 0.9) | à prouver |

**Inventaire initial** (variables du compose VM du 25/09 qui désignent un autre service par son nom Docker ; à compléter par `.env.url`, `mcp_servers` et les défauts du code — action 0.8) :

| Service qui migre (sous-vague) | Appelants qui **restent sur la VM** | Conséquence |
|---|---|---|
| `api-detection-langue-fr-service`, `content-extractor-api-service` (V2-a) | `crawler-service` (reste jusqu'à V2-e) | jumeaux VM **UP** tant que `crawler-service` n'est pas repointé vers les URL Cloud Run |
| `api-classification-service` / `-lb` (V2-a) | `mcp-classification-produit-service` (jusqu'à V2-b) | jumeau VM UP jusqu'à V2-b, ou repointage du MCP |
| `mcp-gateway-service` (V2-c) | `account-service-backend` (jusqu'à V2-d) | au moment de V2-c : repointer `account-service-backend` vers le Service GKE (IP interne) **avant** d'arrêter le jumeau |
| `account-service-backend` (V2-d) | `redis-client-frontend` (front SSO, tant qu'il n'est pas migré) | repointage du front, ou jumeau UP |
| `api-catalog-service` (**reste** sur la VM) | `api-gateway-go-service` (V2-c, vers GKE) | sens inverse : la gateway GKE doit joindre le catalogue par l'enabler (point 6 de la fiche L7) |
| `image-download-service` (**reste**) | `crawler-monitor-backend` (Cloud Run) | sens inverse, déjà câblé vers la VM |

Les consumers L1→L6 n'exposent pas d'HTTP : aucun service de la VM ne les appelle directement (ils passent par le broker).

---

## 8. Ce qui reste sur la VM après la vague 2

Services GPU et modèles, backends gRPC graph-rag (joints par l'enabler `10.11.0.2:1505x`), MySQL `gateway_db`, Neo4j, Elasticsearch, observabilité, `qc-tracking-service` (tant que le tracking n'est pas poussé en HTTP), et trois consumers sans équivalent GKE (`document-echange-processor-service`, `qc-fabricant-reference`, `prix-extraction-siteweb`), candidats à un petit lot avec la méthode L1→L6.
