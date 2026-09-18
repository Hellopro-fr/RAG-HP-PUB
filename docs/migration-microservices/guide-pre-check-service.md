# Guide de pré-contrôle — à faire service par service

> **Pour le développeur, avec Claude.** Compte 20 à 30 minutes par service. Le but n'est pas de migrer quoi que ce
> soit : c'est de trouver, dans ton code, les hypothèses qui ne survivront pas au déplacement de la VM vers le cloud.
>
> **Dis d'abord à Claude** : « lis `docs/migration-microservices/CLAUDE.md` avant de m'aider ». Il y trouvera le
> contexte et les pièges de nommage.

---

## Avant de commencer

Trouve ton service dans [`inventaire-services-migration-par-lot.md`](inventaire-services-migration-par-lot.md)
et note deux choses : son **lot** (P1 → P10) et la colonne **« à savoir »**.

```bash
SERVICE=website-processor-service        # remplace par le tien
grep -n "$SERVICE" docs/migration-microservices/inventaire-services-migration-par-lot.md
```

| Ton lot | Ce que ça implique |
|:--:|---|
| **P1** | Consumer de file. Saute les étapes 1 à 3, fais les étapes 4 à 6. Ton service n'a pas d'adresse |
| **P2, P3** | Fais tout. Attention particulière aux jetons partagés (étape 5) |
| **P4 à P8** | **Fais tout.** C'est là que se trouvent la plupart des défauts |
| **P9** | Ton service attend une décision. Fais quand même le pré-contrôle, il servira |
| **P10** | Ton service reste sur la VM. **Rien à faire** |

---

## Qui est concerné, en vrai

Un balayage du dépôt au 2026-09-18 a trouvé **41 fichiers contenant une adresse de service en dur**, répartis ainsi.
Si ton service est dans cette liste, tu as du travail garanti ; s'il n'y est pas, le pré-contrôle sera probablement rapide.

| Service ou lib | Fichiers concernés |
|---|:--:|
| `libs/auth` | 6 |
| `apps-microservices/opti-moteur-front` | 5 |
| `apps-microservices/mcp-gateway-service` | 5 |
| `apps-microservices/DeepSeek-OCR` | 5 |
| `apps-microservices/nextjs-formulaire-hp` | 3 |
| `apps-microservices/crawler-service` | 3 |
| `apps-microservices/api-gateway-go` | 3 |
| `apps-microservices/account-service-backend` | 3 |
| `libs/common-utils` · `api-catalog-service` | 2 chacun |
| `product-database-qdrant-service` · `mcp-gateway-frontend` · `mcp-classification-produit-service` · `llm-service` · `graph-rag-milvus-service` · `dlq-manager-service` · `deepseek-metrics-collector-service` · `crawler-monitor-frontend` · `crawler-monitor-backend` · `api-gateway` · `api-detection-langue-fr` · `api-classification` · `account-service-frontend` | 1 chacun |

> **`libs/auth` et `libs/common-utils` sont partagées.** Un défaut là-dedans touche tous leurs consommateurs.
> Si tu les modifies, préviens — ce n'est pas un changement local.

---

## Étape 1 — Adresses de services en dur

C'est le défaut numéro un. Sur la VM, Docker résout `http://optimize-service:8563`. Sur Cloud Run et GKE, ce nom
n'existe plus.

```bash
SERVICE=<ton-service>
grep -rnE 'http://[a-z0-9_-]+:[0-9]{2,5}' apps-microservices/$SERVICE/
```

Pour chaque résultat, ouvre [`correspondance-endpoints-vm-cloud.md`](correspondance-endpoints-vm-cloud.md) et
cherche le service appelé. Trois cas :

| Ce que tu trouves | Ce que ça devient |
|---|---|
| Le service appelé passe par la **gateway** | Rien à changer : l'appel `/<nom>-service` continue de fonctionner |
| Le service appelé est un **appel direct** | À remplacer par une variable d'environnement. Ne code pas la nouvelle URL en dur non plus |
| Le service appelé **n'est pas dans le document** | Remonte-le. C'est soit un service oublié, soit un appel mort |

**Exemple réel** — `apps-microservices/api-classification/app/core/classifier.py:120` contient
`http://optimize-service:8563`. `optimize-service` part sur Cloud Run : cette ligne cassera.

---

## Étape 2 — Ports gRPC

```bash
grep -rnE ':(5005[0-9]|50051)' apps-microservices/$SERVICE/
grep -rn "grpc" apps-microservices/$SERVICE/ --include=*.py --include=*.go | head -20
```

⚠️ **Piège connu et confirmé** : quatre clients gRPC de `libs/common-utils` ont une **valeur par défaut `:50051`
qui est fausse**. Les vrais ports sont 50055 à 50058. Le bug reste invisible tant que la variable d'environnement
surcharge le défaut — et se réveille le jour où elle manque.

Si ton service instancie un client gRPC, vérifie que le port vient **toujours** de la configuration, et que le
défaut codé est le bon.

---

## Étape 3 — `localhost` et boucle locale

```bash
grep -rn "localhost\|127\.0\.0\.1" apps-microservices/$SERVICE/ --include=*.py --include=*.go --include=*.ts
```

Sur la VM, plusieurs services partagent l'hôte : `localhost` peut désigner un voisin. Sur Cloud Run, `localhost`
ne désigne que le conteneur lui-même.

**Cas réel** : `api-rest-milvus` appelle `api-recherche` via `http://localhost` alors qu'il tourne déjà sur
Cloud Run. Ignore les `localhost` de tests et de développement local, ils ne posent pas de problème.

---

## Étape 4 — Fichiers et volumes

```bash
grep -rnE '/mnt/|/data/|open\(|Path\(' apps-microservices/$SERVICE/ --include=*.py | head -20
grep -n "volumes:" -A5 docker-compose.yml | grep -B1 -A4 "$SERVICE"
```

**Cloud Run n'a pas de disque persistant** : ce qui est écrit dans le conteneur disparaît à l'arrêt. GKE n'a de
volume que s'il en a été déclaré un explicitement.

Si ton service écrit des fichiers qui doivent survivre, c'est une décision d'architecture — remonte-la, ne la
résous pas seul.

---

## Étape 5 — Variables d'environnement

Sur la VM, **tous les conteneurs héritent d'un `.env` unique** via `env_file`. Sur le cloud, chaque service reçoit
**uniquement** les variables qu'on lui déclare. Une variable que tu utilises sans qu'elle soit déclarée existe
aujourd'hui par accident, et disparaîtra.

```bash
# ce que ton code lit
grep -rhoE 'os\.environ\[.[A-Z_]+|os\.getenv\(.[A-Z_]+|process\.env\.[A-Z_]+|Getenv\("[A-Z_]+' \
  apps-microservices/$SERVICE/ | grep -oE '[A-Z_]{3,}' | sort -u

# ce que la matrice prévoit
grep -n "$SERVICE" docs/migration-microservices/env-migration-matrix.md
```

Compare les deux listes. Toute variable lue par le code et absente de la matrice est **à remonter**.

⚠️ **Les secrets** (clés d'API, mots de passe, jetons) viennent de Secret Manager. La matrice donne le **nom** du
secret, jamais sa valeur. Si tu trouves un secret en clair dans le code, **signale-le sans le recopier**.

Pour les lots **P2 et P3** : `ENCRYPTION_KEY`, `GOOGLE_TEMPLATES_RUNNER_ADMIN_TOKEN` et `ZOHO_GATEWAY_TOKEN`
doivent être **identiques** entre la gateway et ses satellites. Une divergence casse la synchronisation en silence.

---

## Étape 6 — Écritures

```bash
grep -rniE 'insert|update|delete|publish|basic_publish|\.post\(|\.put\(' apps-microservices/$SERVICE/ --include=*.py | head -20
```

Liste ce que ton service **écrit** : base de données, file, webhook, fichier. Pour chaque écriture, réponds à
une question simple — **que se passe-t-il si ce message est traité deux fois ?**

C'est la question centrale de la bascule : pendant quelques minutes, une chaîne peut rejouer un message. Si ton
traitement n'est pas idempotent, il faut le savoir **avant**, pas après.

⚠️ **Écritures jamais exercées en shadow** : les écritures vers **Neo4j** et vers le **back-office PHP**
(webhooks HMAC) n'ont jamais tourné sur des données de production. Si ton service en fait partie, dis-le
explicitement dans ta remontée.

---

## Fiche de remontée

Copie ce modèle, remplis-le, envoie-le au Lead Dev.

```markdown
## Pré-contrôle — <nom du service tel qu'il figure dans l'inventaire>
Lot : P<n>          Dev : <toi>          Date : <aaaa-mm-jj>

### Points trouvés
| Fichier:ligne | Ce qui est en dur | Proposition |
|---|---|---|
| app/core/x.py:120 | http://optimize-service:8563 | variable OPTIMIZE_URL |

### Variables lues par le code et absentes de la matrice
- <VAR> : <à quoi elle sert>

### Écritures et idempotence
- <cible> : rejouable sans dégât ? oui / non / à vérifier

### Questions ouvertes
- ...

### Verdict
⬜ Rien à signaler   ⬜ Corrections à faire (listées)   ⬜ Décision nécessaire
```

**Un pré-contrôle vide est un résultat valide.** Beaucoup de services sont propres, en particulier les consumers
du lot P1. Ne cherche pas un problème pour en trouver un.

---

## Ce que tu ne fais pas

Aucune commande `gcloud`, `kubectl`, `terraform`, ni `docker` sur la production. Aucune modification du
`docker-compose.yml`. Aucun déploiement. L'infrastructure est portée par l'équipe DevSecOps : ton travail s'arrête
à la remontée.
