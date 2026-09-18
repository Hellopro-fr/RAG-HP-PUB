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

## Le calendrier

| Quand | Quoi |
|---|---|
| **Cet après-midi (18/09)** | Réunion de décision : bascule **d'un coup** ou **par lots sur plusieurs jours**. Voir [`strategie-bigbang-vs-par-lot.md`](strategie-bigbang-vs-par-lot.md) |
| **Après la réunion** | Le calendrier définitif est publié ici. Tu seras prévenu du lot et de la date de ton service |
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
