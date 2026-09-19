# Migration des microservices — VM GPU → Cloud Run / GKE

> **Pour toute l'équipe de développement.** Ce dossier contient ce dont tu as besoin pour savoir si ton service
> est concerné, quand, et ce que tu as à vérifier dans ton code avant la bascule.
>
> Publié sur la branche `prod` le 2026-09-18. Un `git pull` suffit pour l'avoir à jour.

---

## En trois phrases

On déplace ~80 services de la **VM GPU** (Docker Compose, ~155 conteneurs) vers **Cloud Run** et **GKE**.
Les services concernés tournent déjà en double sur le cloud depuis juillet-août, **sans trafic** : c'est ce qu'on
appelle le *shadow*. La bascule consiste à leur donner les vraies données de production et à arrêter leurs jumeaux
sur la VM.

**Ce qui ne bouge pas** : le GPU et tout ce qui en dépend restent sur la VM, définitivement.

---

## Par où commencer

| Étape | Document | Temps |
|:--:|---|---|
| **1** | [`inventaire-services-migration-par-lot.md`](inventaire-services-migration-par-lot.md) — trouve ton service, note son **lot** (P1 → P10) | 2 min |
| **2** | [`guide-pre-check-service.md`](guide-pre-check-service.md) — la procédure de vérification, à faire **avec Claude** | 20-30 min par service |
| **3** | [`correspondance-endpoints-vm-cloud.md`](correspondance-endpoints-vm-cloud.md) — l'ancienne adresse de chaque service et la nouvelle | consultation |
| **4** | [`env-migration-matrix.md`](env-migration-matrix.md) — les variables d'environnement, service par service | consultation |

Le fichier [`CLAUDE.md`](CLAUDE.md) de ce dossier sert à ton assistant : il lui donne le contexte, le vocabulaire
et les pièges. Tu n'as pas besoin de le lire, mais **dis à Claude de le lire** avant de commencer.

---

## Ce qu'on attend de toi

**Un pré-contrôle de ton service**, pas une migration. L'infrastructure est déjà faite ; ce qu'on cherche, ce sont
les **hypothèses codées en dur** qui ne survivront pas au déplacement : une URL de conteneur Docker, un port gRPC,
un `localhost`, un chemin de fichier local.

Concrètement, trois questions :

1. Mon service appelle-t-il d'autres services par une adresse écrite en dur dans le code ?
2. Mes variables d'environnement correspondent-elles à ce que la matrice prévoit ?
3. Mon service écrit-il quelque part — base, fichier, webhook — d'une manière qui supposerait qu'il tourne sur la VM ?

**Si ton service est en lot P1, la réponse est probablement « rien à faire »** : les 34 services de ce lot sont des
consommateurs de files RabbitMQ. Ils n'ont pas d'adresse, personne ne les appelle, ils s'abonnent à une queue.
Vérifie quand même les points 2 et 3.

---

## Si l'option « par lots » est retenue

La réunion du 18/09 tranche entre une bascule d'un coup le week-end et une bascule **par lots, par chaîne, en heures
ouvrées**. La seconde option est préparée en détail :

| Document | Ce qu'il contient |
|---|---|
| [`plan-bascule-par-lots.md`](plan-bascule-par-lots.md) | Les 7 lots, le calendrier (lun 21/09 → mer 30/09), les règles, le gel, la communication |
| [`lots/L1.md`](lots/L1.md) … [`lots/L7.md`](lots/L7.md) | Une fiche par lot : composition exacte, secrets, vigilances, prérequis, feuille de lot |
| [`procedure-bascule-un-lot.md`](procedure-bascule-un-lot.md) | La procédure commune, étape par étape, rollback inclus — exécutée par le DevSecOps |
| [`suivi-bascule-par-lots.md`](suivi-bascule-par-lots.md) | Le tableau qui dit **qui est où** pendant la coexistence VM / GKE |
| [`rapports/`](rapports/) | **Un rapport par service basculé** : ce qui a changé, ce qui est prouvé, et **comment tu accèdes maintenant à ton service** (logs, shell, file) — [`deepseek-metrics-collector-service`](rapports/deepseek-metrics-collector-service.md) · [`nettoyage-bruit-ocr-service`](rapports/nettoyage-bruit-ocr-service.md) |

⚠️ **Deux numérotations** : les **P1…P10** de l'inventaire sont des *priorités* ; les **L1…L7** du plan sont des
*lots d'exécution*, qui ne couvrent que P1, P2 et P3. Si ton service est en P4 ou au-delà, cette série ne te
concerne pas encore.

**Ce que ça change pour toi si tu es en P1-P3** : ton pré-contrôle doit être remis **avant la veille du lot de ton
service**, et un référent de ta chaîne doit être joignable entre 14h et 16h le jour du lot, puis le lendemain matin.
La fiche de ton lot dit quel jour.

## Le calendrier

| Quand | Quoi |
|---|---|
| **Cet après-midi (18/09)** | Réunion de décision : bascule **d'un coup** ou **par lots sur plusieurs jours**. Voir [`strategie-bigbang-vs-par-lot.md`](strategie-bigbang-vs-par-lot.md) |
| **Sam 19/09** | **Lot L1 basculé** (`deepseek-metrics-collector-service`, `nettoyage-bruit-ocr-service`). Rapports dans `rapports/` |
| **Lun 21/09 9h30** | Validation fonctionnelle L1 sur le premier message réel · **décision LEAD sur le tracking fichier (F-HP-MIG-008) avant L2** |
| **Mar 22/09 14h** | L2 (QC) si décision prise — sinon report |
| **Avant la bascule de ton lot** | Ton pré-contrôle doit être remonté |

---

## Où remonter ce que tu trouves

Ouvre un point avec le **Lead Dev** en citant :

- le **nom de ton service** tel qu'il apparaît dans l'inventaire,
- le **fichier et la ligne** concernés,
- ce que tu as trouvé, et ce que tu proposes.

**Une erreur dans ces documents est aussi une remontée utile.** Ils ont été construits à partir du
`docker-compose.yml` et de l'état réel du cloud ; si ton service fait quelque chose qu'ils ignorent, c'est
exactement ce qu'on veut apprendre **maintenant**, pas pendant la bascule.

---

## Ce que ces documents ne sont pas

Ils ne décrivent **pas** comment déployer ton service : l'infrastructure, les secrets et les pipelines sont gérés
par l'équipe DevSecOps. Tu n'as aucune commande `gcloud`, `kubectl` ou `terraform` à lancer. Si un document te
demande d'en lancer une, c'est une erreur — signale-la.

Le détail opérationnel de la bascule (qui fait quoi, heure par heure) vit côté DevSecOps, hors de ce dépôt.
