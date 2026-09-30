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
| 0.3 | **Load balancer HTTPS prod** (une IP publique fixe, un routage par nom d'hôte) avec les back-ends Cloud Run (`rag`, `login`, `formulaire`, `nextjs-conseils`) | DSO | module TF `https_lb_cloud_run` (déjà éprouvé sur `crlb-demo.hellopro.eu`), `plan` relu puis `apply -target` | TF | jeu 1/10 | IP du LB ; chaque hôte répond via `curl --resolve <hôte>:443:<IP LB>` |
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
| d.5 | `formulaire.hellopro.eu` | **devs** (Next 15) puis DSO | A → IP LB | Gandi | migration Next 15 livrée (F-HP-SEC-019) |
| d.6 | `conseils.hellopro.fr` | **PROD** décide, DSO exécute | A de **`nextjs-conseils.hellopro.eu`** → IP LB (voir § 5) ; Ecritel seulement si sa règle vise une IP | Gandi (± Ecritel) | GO PROD/SEO + réponse Ecritel |

### V2-e — Stockage images et crawler · après la vague 2

| # | Quoi | Qui | Comment | Où | Quand |
|---|---|---|---|---|---|
| e.1 | Cible GCS pour `image_download_data` (237 Go au 20/07) et `crawler_data` (374 Go) | DSO propose, CTO valide | bucket + montage ou API GCS ; données reconstituables | TF | semaine du 19/10 |
| e.2 | Adaptation du code (`image-download` ×10, `image-cdn`, `crawler-service`) | devs | lecture / écriture GCS | code | à planifier |

---

## 4. Calendrier et mobilisation

| Date | DSO | LEAD / devs | CTO / PROD | Ecritel |
|---|---|---|---|---|
| **Jeu 1/10** | revue ; mesures VM ; LB + certificats ; test VM → CR ; message Ecritel ; relevé réserve embedding | revue ; nommer un dev par service P4/P5 ; lancer les correctifs d'URL | revue ; décisions § 6 | reçoit la question |
| **Ven 2/10** | NEG GKE ; **TTL Gandi 300 s** ; Cloud Armor PREVIEW ; runbook | correctifs d'URL | — | répond |
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
| ven 2/10 | A de `api`, `mcp`, `rag`, `login`, `cmf`, `formulaire`, `nextjs-conseils` (`.hellopro.eu`) | **TTL → 300 s**, valeur inchangée |
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

## 6. Décisions attendues à la revue du 1/10

| # | Décision | Qui |
|---|---|---|
| 1 | Plan et calendrier validés ; un dev nommé par service P4/P5 | CTO, LEAD |
| 2 | Bascule de `conseils` : quand, et sous quelles conditions SEO | PROD, LEAD |
| 3 | Date de livraison de la migration Next 15 du formulaire | LEAD |
| 4 | P9 : `api-gateway-service` (Python), `api-model`, `api-chatbot`, suppression de `graph-rag-api-recherche-service-debug`, cibles `SERVICE_CRAWLING` / `SERVICE_OPTIMOTEUR` | LEAD |
| 5 | `dlq-manager-service` (auto-archivage Elasticsearch) : activer ou non ; sinon retirer `dlq.hellopro.eu` | métier, CTO |
| 6 | Cloud Armor : critères pour passer en blocage réel | RSSI |
| 7 | CD GKE prod (F-HP-IND-005) : calage en parallèle | CTO |

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

## 8. Ce qui reste sur la VM après la vague 2

Services GPU et modèles, backends gRPC graph-rag (joints par l'enabler `10.11.0.2:1505x`), MySQL `gateway_db`, Neo4j, Elasticsearch, observabilité, `qc-tracking-service` (tant que le tracking n'est pas poussé en HTTP), et trois consumers sans équivalent GKE (`document-echange-processor-service`, `qc-fabricant-reference`, `prix-extraction-siteweb`), candidats à un petit lot avec la méthode L1→L6.
