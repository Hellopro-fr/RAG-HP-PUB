# Procédure de bascule d'un lot — la même pour les sept

> **Exécutée par le DevSecOps**, en présence du référent dev du lot. Les développeurs n'ont **aucune** de ces
> commandes à lancer : ce document est publié pour que chacun sache ce qui se passe, dans quel ordre, et quand
> son tour arrive.
>
> Les commandes ci-dessous sont des **gabarits** (`<LOT>`, `<nom>`). Les cartes d'exécution exactes — quoi, où,
> quand, impact — sont produites au moment de chaque lot, à partir de la fiche `lots/L<n>.md`.
> Aucun secret n'apparaît ici : les valeurs viennent de Secret Manager au moment de l'exécution.

---

## Retours d'expérience intégrés (L4, 24/09)

- **Écrivains qui suppriment ou mettent à jour** : « supprimer `id > borne` » ne défait pas une suppression. Filet retenu : **sauvegarde Milvus à la demande juste après P2** (`kubectl -n milvus-prod create job --from=cronjob/milvus-backup-daily <nom>`, ~4 min 10), VM arrêtée, avant la première écriture GKE — point de retour exact. Les files attendent pendant la sauvegarde, sans perte. Le job du CronJob crée sans jamais purger.
- **P3 scripté avec garde-fous** : lecture Secret Manager, empreintes attendues vérifiées **avant** tout patch (arrêt sinon), copie in-cluster `<secret>-prel4` de chaque secret, patch clé par clé et **relecture de chaque empreinte posée**. Aucune valeur affichée ni écrite sur disque hors fichier de patch 600 supprimé.
- **URL broker prod** : valeur `platform-rabbitmq-url` réécrite en DNS interne ; vérifiée égale au secret prod du lot précédent avant patch.
- **Mémoire du cluster** : requests à 86-93 % → montée en réplicas **par paliers** avec `kubectl top nodes` entre deux ; un service à file vide reste à 1 (monté sur constat de backlog).
- **Parité aussi côté VM** : empreintes des variables lues **dans les conteneurs VM qui tournent** (`docker exec … printenv`, jamais la valeur) comparées à Secret Manager — Redis n'avait jamais été comparé.
- **Pré-contrôle écrit du LEAD** avec la question d'idempotence posée par écrivain (message prêt à envoyer) : réponses en 1 h.
- **Git Bash** : un `python -c` multi-ligne local échoue (shim Windows) ; utiliser `jq`/`jsonpath` en local, le multi-ligne seulement dans un `kubectl exec`.
- **Manifeste d'un service sous wrapper CD** (`product-processor-service`) : son tag d'image dans le dépôt peut être en retard sur le cluster ; l'aligner avant tout `kubectl apply`, sinon l'apply ramène une vieille image.
- **Chrono L4** : arrêt VM → preuve broker **~12 min 25** (39 conteneurs, 9 services, dont 4 min 10 de sauvegarde).

## Retours d'expérience intégrés (L3, 23/09)

- **Les défauts du code aussi** : un service peut vivre sur une valeur **par défaut** qui n'existe que sur la VM (noms Docker des clients gRPC `common_utils.grpc_clients` : `database-recherche-service:50054`…). P1 : `grep -rE "grpc_clients|_SERVICE_URL" apps-microservices/<svc>/app` ; chaque client utilisé = variable d'adresse déclarée dans le manifeste, vers le proxy de la VM `10.11.0.2:15051-15054` (F-HP-MIG-012).
- **Parité des variables utilisées, pas seulement présentes** : lire le code (`os.environ`, `settings.py`) pour lister ce que le service **consomme** ; la VM passe tout le `.env` commun, le manifeste doit porter ce qui est lu (F-HP-MIG-011 : `prix-caracterisation` sans `DEEPSEEK_API_KEY` ni `ZILLIZ_*`).
- **Premier écrivain d'une base** : relever une borne (`max id` auto-généré) **après** l'arrêt des jumeaux, via un conteneur jetable portant les mêmes variables ; vérifier la sauvegarde de la nuit ; le rollback données devient une suppression `id > borne`.
- **Le provider LLM de chaque service, pas celui du voisin** : trois services d'une même famille peuvent forcer des providers différents (`prix-extraction-message`/`-devis` → Gemini, `prix-extraction-produits` → DeepSeek). Lire la constante `LLM_PROVIDER` et le défaut `settings` **service par service** ; toute clé du provider utilisé est déclarée dans le manifeste (F-HP-MIG-011 bis, 24/09).
- **Couper avant de corriger** : un service qui part en DLQ se met à `replicas=0` (la file accumule sans perte), on corrige, on remet à 1 ; les autres services du lot continuent.
- **Chrono L3** : arrêt VM → preuve broker **~4 min 10** (8 conteneurs, 5 services, Milvus inclus).

## Retours d'expérience intégrés (L2, 21/09 — rollback)

- **Les noms de variables ne suffisent pas : P1 compare les VALEURS par empreinte.** Le 21/09, le secret K8s partagé `platform-llm-hp-secrets` portait encore ses placeholders (`hp-token` 35 caractères au lieu de 144) ; tous les appels API depuis GKE ont répondu 400, rollback à 14h57. Pour chaque variable secrète du lot : longueur + SHA-256 côté conteneur VM (`docker exec … printf "%s" "$VAR" | sha256sum`) et côté secret K8s (`kubectl get secret … | base64 -d | sha256sum`), **jamais la valeur**. Un écart = stop (F-HP-MIG-009).
- **Après `scale 0`, attendre la disparition des pods avant `docker start`** : SIGTERM ignoré = 30 s de grâce ; le 21/09, 20 s de double consommation. `kubectl wait --for=delete pod -l app=<svc> -n apps-microservices --timeout=60s` pour chaque déploiement, ou vérifier `kubectl get pods | grep -c ^qc-` = 0.
- **Preuve avant/après par sonde** : un pod jetable qui rejoue l'appel du service avec le secret K8s (`kubectl apply` d'un Pod `curlimages/curl` avec `secretKeyRef`) donne le code HTTP et le corps de réponse que les logs du service n'affichent pas (`Invalid format for the given token`).
- **Git Bash / Windows** : `jq --slurpfile x <(…)` échoue (`/proc/<pid>/fd` illisible) → boucle `while read` par déploiement ; `gcloud --format='yaml(...)'`/`table(...)` peut sortir **vide sans erreur** → `--format=json` ou sortie brute ; un fichier `/tmp` écrit sous Windows porte des `\r` (`tr -d '\r'`).
- **Le cluster est zonal (`europe-west1-b`)** : `--zone`, pas `--region`, sinon gcloud répond vide.
- **Chronos L2** : bascule 2 min 39 (arrêt VM → 9 files reprises), rollback 1 min 31.

## Retours d'expérience intégrés (L1-a, 19/09)

- **`rabbitmqctl` sépare par des tabulations** : `grep 'nom '` (espace) ne matche rien et laisse croire à une absence. Utiliser `grep -E '^nom\s'`.
- **`kubectl logs deploy/…` pendant un rollout peut lire l'ancien pod** : pour la preuve, cibler le pod `Running` le plus récent par son nom.
- **Fenêtre tarifaire DeepSeek** : 4 services se désabonnent 01h-04h et 06h-10h UTC. Basculer hors fenêtre, sinon la preuve broker attend.
- **La cible d'un service peut encore être un placeholder shadow** : le pré-flight compare l'env GKE à l'env VM **avant** P2 (L1-a : `DEEPSEEK_METRICS_COLLECTOR_URL`).
- **Jamais de valeurs d'environnement à l'écran.** Le `.env` unique de la VM injecte ~40 secrets dans chaque conteneur ; un masque par motif de nom **rate toujours quelque chose** (le 19/09 : `NEO4J_PASSWORD`, à cause d'un chiffre dans le nom). Comparer les **noms** (`docker inspect … | cut -d= -f1`), puis lire une à une les seules variables non secrètes que le **code lit réellement** (grep `os.environ` dans l'app et ses modules `common_utils`).
- **Chronos mesurés** : arrêt VM → preuve broker **3 min** (1re fois), **1 min 50** (rebascule) ; rollback complet **~2 min** (VM réabonnée en 62 s).

## Les deux invariants

**Arrêter la VM avant de repointer GKE.** Un consumer s'abonne à une file ; deux jumeaux actifs se partagent les
messages sans qu'aucune erreur n'apparaisse. L'ordre est le même, inversé, au rollback.

**Aucune liste recopiée.** Conteneurs VM, déploiements GKE, secrets : tout est **dérivé** au moment de l'exécution
depuis la fiche de lot et l'état réel, puis **compté** avant d'agir. Le 17/09, une liste recopiée avait oublié un
service à quatre réplicas.

---

## Vue d'ensemble

| Étape | Quoi | Où | Durée | Niveau |
|:--:|---|---|:--:|:--:|
| **P0** | La veille : prérequis, re-scan, snapshots, message | Poste · Cloud Build | 1 h | 🟢 |
| **P1** | Pré-flight : contexte, listes dérivées, comptes, état de référence | Poste (`kubectl-local`) · VM GPU | 10 min | 🟢 |
| **P2** | **Arrêt des jumeaux VM** du lot | VM GPU (`devhp`) | 2 min | 🟠 |
| **P3** | Repointage des secrets + variables data, rollout | Poste (`kubectl-local` + `default`) | 5 min | 🟠 |
| **P4** | Contrôle broker : consumers > 0, backlog décroît | Poste (`kubectl-local`) | 5 min | 🟢 |
| **P5** | Montée en réplicas à la cible de départ, observation 20 min | Poste (`kubectl-local`) | 25 min | 🟡 |
| **P6** | Validation fonctionnelle, message contrôlé si écriture | LEAD · dev | 30 min | — |
| **P7** | Message J-soir, observation jusqu'à J+1 9h30 | — | nuit | — |
| **R** | **Rollback du lot** — inverse exact de P2 → P3 | VM GPU · Poste | ~2 min | 🟠 |

Entre P2 et P4, les queues du lot **accumulent** : c'est attendu, et c'est bref (P3 dure quelques minutes).

---

## P0 — La veille

| | |
|---|---|
| **Quoi** | Tout ce qui ne dépend pas du jour J : prérequis de la fiche, re-scan, sauvegardes, communication |
| **Pourquoi** | Le jour J ne doit contenir que des gestes déjà préparés. Une surprise la veille se corrige ; la même surprise à 14h15 se rollbacke |
| **Où** | Poste (`gcloud` config `default` pour Cloud Build et Secret Manager) |

1. **Fiche de lot relue** — composition, secrets, vigilances, prérequis spécifiques.
2. **Pré-contrôles reçus** du LEAD pour chaque service du lot. Pas de pré-contrôle, pas de lot.
3. **Re-scan Trivy** des seules images du lot (Cloud Build `cb-rescan-images.yaml`, liste réduite). Critère :
   **0 CRITICAL hors VEX du 17/09**.
4. **Snapshots** si le lot écrit : Milvus (L3, L4), Neo4j (L5, L7), `gateway_db` (L7).
5. **Gel vérifié** : aucun merge `prod` touchant les services du lot depuis le re-scan.
6. **Message J-1** aux devs concernés (modèle dans le plan, §9).
7. **Ligne du lot** dans le tableau de suivi : `⬜ à venir` → `🟡 prêt`.

8. **Registre des services qui restent sur la VM** (tableau de suivi) relu : aucun n'entre dans la liste des jumeaux à arrêter ; noter ce que le lot leur doit (file, URL, tracking).

---

## P1 — Pré-flight (J, 14h00)

| | |
|---|---|
| **Quoi** | Vérifier le contexte, dériver les trois listes du lot, les compter, photographier l'état du broker |
| **Pourquoi** | Les trois listes (déploiements GKE, secrets, conteneurs VM) sont la matière de P2 et P3. Si un compte ne correspond pas à la fiche, on **s'arrête avant de toucher quoi que ce soit** |
| **Où** | Poste, Git Bash, config `kubectl-local` — puis VM GPU en `devhp` pour la liste des conteneurs |
| **Niveau** | 🟢 lecture seule |

```bash
# --- poste, config kubectl-local ---
gcloud config configurations activate kubectl-local
kubectl config current-context                      # doit contenir matching-api-dev-k8s
NS=apps-microservices
LOT=L<n>

# 1) déploiements GKE du lot — recopiés depuis la colonne « Déploiement GKE » de la fiche
cat > /tmp/${LOT}-deploys.txt <<'EOF'
<nom-gke-1>
<nom-gke-2>
EOF
wc -l < /tmp/${LOT}-deploys.txt                    # = nombre de services de la fiche

# 2) secrets du lot — DÉRIVÉS du cluster, jamais recopiés (deux conventions coexistent)
kubectl get deploy -n "$NS" -o json | jq -r --slurpfile d <(jq -R . /tmp/${LOT}-deploys.txt | jq -s .) '
  .items[] | select(.metadata.name as $n | $d[0] | index($n))
  | .spec.template.spec.containers[].env[]? | select(.name|test("RABBIT|AMQP";"i"))
  | .valueFrom.secretKeyRef | "\(.name)\t\(.key)"' | sort -u | tee /tmp/${LOT}-secrets.txt
wc -l < /tmp/${LOT}-secrets.txt                    # = nombre de services du lot (1 secret chacun)

# 3) état de référence du broker prod — TOUTES les queues (les queues du lot seront dérivées en P2)
POD=$(kubectl get pods -n rabbitmq-v3 -o name | head -1)
kubectl exec -n rabbitmq-v3 "$POD" -- rabbitmqctl list_queues -q name messages consumers \
  | sort > /tmp/${LOT}-broker-before.txt
wc -l < /tmp/${LOT}-broker-before.txt               # ~124 queues au 17/09
```

> **Les queues du lot ne sont pas recopiées non plus.** On ne les connaît avec certitude qu'en observant le broker :
> ce sont celles dont le nombre de consommateurs **tombe à zéro quand on arrête les jumeaux VM** (P2). La différence
> avant/après les donne, sans dépendre d'une configuration lue dans le code.

```bash
# --- VM GPU, en devhp, ~/RAG-HP-PUB ---
# 4) conteneurs VM du lot — noms de SERVICES compose (colonne 1 de la fiche), DÉVELOPPÉS en conteneurs réels
cat > /tmp/${LOT}-vm-services.txt <<'EOF'
rag-hp-pub-<service-1>
rag-hp-pub-<service-2>
EOF
docker ps --format '{{.Names}}' | grep -Ff /tmp/${LOT}-vm-services.txt | tee /tmp/${LOT}-vm-containers.txt
wc -l < /tmp/${LOT}-vm-containers.txt              # = colonne « Réplicas VM » additionnée
```

**Critère de passage** : les trois comptes correspondent à la fiche de lot. Sinon **stop** — un écart est une
information, pas un obstacle à contourner.

```bash
# 5) parité des VALEURS secrètes VM vs K8s — empreintes seulement (F-HP-MIG-009). Pour chaque service du lot :
#    côté K8s : les couples (secret, clé) référencés par le déploiement
kubectl get deploy <nom-gke> -n "$NS" -o json | jq -r '.spec.template.spec.containers[].env[]? | select(.valueFrom.secretKeyRef) | "\(.name)\t\(.valueFrom.secretKeyRef.name)\t\(.valueFrom.secretKeyRef.key)"' \
  | while IFS=$'\t' read -r VAR SEC KEY; do printf '%-28s K8S len=%s sha=%s\n' "$VAR" "$(kubectl get secret "$SEC" -n "$NS" -o jsonpath="{.data.$KEY}" | base64 -d | tr -d '\r\n' | wc -c)" "$(kubectl get secret "$SEC" -n "$NS" -o jsonpath="{.data.$KEY}" | base64 -d | tr -d '\r\n' | sha256sum | cut -c1-16)"; done
#    côté VM (devhp) : mêmes variables, dans le conteneur réel
docker exec rag-hp-pub-<service>-1 sh -c 'for v in HP_TOKEN DEEPSEEK_API_KEY GEMINI_API_KEY RABBITMQ_URL; do printf "%-28s VM  len=%s sha=%s\n" "$v" "$(printf "%s" "$(eval echo \$$v)" | wc -c)" "$(printf "%s" "$(eval echo \$$v)" | sha256sum | cut -c1-16)"; done'
# Critère : mêmes longueurs et mêmes empreintes pour toutes les variables secrètes (RABBITMQ_URL diffère volontairement : dev vs prod jusqu'à P3).
# Toute valeur de 33 ou 35 caractères avec l'empreinte fc40185a… ou f7636db3… est un PLACEHOLDER → stop.
```

> Deux pièges de nommage vérifiés au pré-flight : `webhook-service` et `mcp-google-templates-runner` n'ont **pas**
> le préfixe `rag-hp-pub-` ; `prix-milvus-processor` et `graph-rag-dlq-manager` perdent leur `-service` sur GKE.

---

## P2 — Arrêt des jumeaux VM

| | |
|---|---|
| **Quoi** | `docker stop` des conteneurs listés en P1-4, et rien d'autre |
| **Pourquoi** | Libérer les files de production **avant** que GKE s'y abonne. C'est le premier des deux invariants |
| **Où** | VM GPU, `devhp` |
| **Niveau** | 🟠 — les queues du lot accumulent pendant quelques minutes, jusqu'à P4. Aucune perte : les messages restent en file |
| **Réversible** | Oui, immédiatement : `xargs -a /tmp/${LOT}-vm-containers.txt docker start` |

```bash
# --- VM GPU ---
xargs -a /tmp/${LOT}-vm-containers.txt docker stop -t 30  # stop, JAMAIS rm ; -t 30 : grâce SIGTERM (certains services l'ignorent → Exited 137, sans conséquence sur file vide)
docker ps -a --format '{{.Names}}\t{{.Status}}' | grep -Ff /tmp/${LOT}-vm-services.txt   # tous « Exited »
```

```bash
# --- poste : dériver les queues du lot = celles dont les consommateurs sont tombés à 0 ---
kubectl exec -n rabbitmq-v3 "$POD" -- rabbitmqctl list_queues -q name messages consumers \
  | sort > /tmp/${LOT}-broker-after-stop.txt
join /tmp/${LOT}-broker-before.txt /tmp/${LOT}-broker-after-stop.txt \
  | awk '$3 > 0 && $5 == 0 && $1 !~ /_dlq$/ {print $1}' | tee /tmp/${LOT}-queues.txt
wc -l < /tmp/${LOT}-queues.txt                      # ≥ nombre de services du lot (certains en consomment plusieurs)
```

**Critère** : tous `Exited`, aucun absent ; la liste des queues du lot est **non vide** et cohérente avec les
services arrêtés (les noms se reconnaissent). Une queue inattendue dans la liste = un service arrêté qui n'aurait
pas dû l'être → **rollback immédiat de P2** (`docker start`) et analyse.

> Pour L6, `llm_templating_queue` peut déjà être à 0 consommateur **avant** P2 si l'on est avant 13h : elle
> n'apparaîtra pas dans la différence. C'est une raison de plus pour jouer L6 l'après-midi.

---

## P3 — Repointage des secrets et des variables, rollout

| | |
|---|---|
| **Quoi** | Pour chaque secret du lot : patcher la clé `rabbitmq-url` vers le broker prod. Pour les lots à données : basculer les variables Milvus / Neo4j / Redis / ES selon la matrice. Puis redémarrer |
| **Pourquoi** | C'est le second geste de la bascule. `kubectl patch` ne touche que la clé visée ; reconstruire le secret effacerait `zilliz-user`, `zilliz-password` et `redis-url` sur les sept secrets multi-clés |
| **Où** | Poste, `kubectl-local` (patch, rollout) et `default` (lecture Secret Manager) |
| **Niveau** | 🟠 — à partir du rollout, les pods GKE consomment la **production** |
| **Réversible** | Oui : même boucle avec la valeur dev, puis rollout |

```bash
# valeur prod lue depuis Secret Manager — jamais tapée, jamais affichée
gcloud config configurations activate default
PROD_URL="$(gcloud secrets versions access latest --secret=<nom-du-secret-broker-prod>)"
gcloud config configurations activate kubectl-local

while read -r SECRET KEY; do
  kubectl patch secret "$SECRET" -n "$NS" --type merge \
    -p "{\"stringData\":{\"$KEY\":\"$PROD_URL\"}}"
done < /tmp/${LOT}-secrets.txt
unset PROD_URL

# variables data (Milvus / Neo4j / Redis / ES) : selon env-migration-matrix.md, service par service
# — commandes exactes produites au moment du lot, depuis la fiche

while read -r D; do kubectl rollout restart deploy/"$D" -n "$NS"; done < /tmp/${LOT}-deploys.txt
kubectl wait --for=condition=Available -n "$NS" \
  $(sed 's#^#deploy/#' /tmp/${LOT}-deploys.txt | tr '\n' ' ') --timeout=300s
```

**Critère** : autant de `patched` que de lignes dans la liste des secrets ; tous les déploiements `Available`.

---

## P4 — Contrôle broker

| | |
|---|---|
| **Quoi** | Vérifier sur le broker **prod** que les queues du lot ont retrouvé des consommateurs et que le backlog décroît |
| **Pourquoi** | Seule preuve que la bascule a pris. Le pod `Running` ne suffit pas : il peut tourner sans être abonné |
| **Où** | Poste, `kubectl-local` — `rabbitmqctl` dans le pod. **Pas de `curl` sur `10.0.1.216:15672`** : ce port n'est pas exposé |
| **Niveau** | 🟢 |

```bash
kubectl exec -n rabbitmq-v3 "$POD" -- rabbitmqctl list_queues -q name messages consumers \
  | grep -Ff /tmp/${LOT}-queues.txt | grep -v '_dlq'   # sortie rabbitmqctl séparée par TABULATIONS : ne jamais grep un nom suivi d'un espace
# attendu : consumers >= 1 partout, messages qui baissent entre deux relevés à 60 s

# logs d'un pod du lot : connexion au broker PROD, mot de passe masqué à l'affichage
kubectl logs -n "$NS" deploy/<nom-gke> --since=5m 2>&1 \
  | sed -E 's#(amqp://[^:]+):[^@]*@#\1:***@#g' | grep -iE "connect|consum|queue" | tail -5
```

**Critère** : `consumers ≥ 1` sur chaque queue du lot (hors `_dlq`), et une seconde lecture 60 s plus tard montre
`messages` en baisse. Pour L6, `llm_templating_queue` **peut** légitimement afficher 0 avant 13h.

---

## P5 — Montée en réplicas

| | |
|---|---|
| **Quoi** | Passer chaque déploiement du lot à sa cible de départ (colonne « Cible réplicas GKE » de la fiche), puis observer 20 minutes |
| **Pourquoi** | GKE reprend à `replicas: 1` une charge que la VM assurait avec plusieurs conteneurs. La cible de départ est la moitié des réplicas VM — un pod GKE vaut plusieurs conteneurs VM I/O-bound — puis on ajuste sur la profondeur des queues |
| **Où** | Poste, `kubectl-local` |
| **Niveau** | 🟡 — mémoire du cluster : ~265 Mi par pod, l'autoscaler du pool (`min 4 / max 6`) absorbe un dépassement |

```bash
kubectl scale deploy/<nom-gke> --replicas=<cible> -n "$NS"     # pour chaque ligne de la fiche
# 20 min plus tard : les queues du lot doivent drainer. Sinon +1 ou +2 réplicas, pas de rollback à ce stade.
```

**Critère** : backlog en baisse continue sur 20 minutes. Un backlog stable ou croissant après ajustement est un
motif de rollback (§R).

---

## P6 — Validation fonctionnelle

| | |
|---|---|
| **Quoi** | Un scénario métier de bout en bout sur la chaîne du lot, exécuté par le référent dev ou le LEAD |
| **Pourquoi** | Le broker qui draine prouve que les messages sont consommés, pas qu'ils sont **bien** traités |
| **Qui** | LEAD · dev référent — le DSO regarde les logs pendant ce temps |

Pour les lots à écriture (L3, L4, L5, L6, L7) : **un message contrôlé d'abord**, dont on connaît le résultat attendu
— la ligne Milvus, le nœud Neo4j, la mise à jour côté back-office — et vérification qu'il est là **une fois**.
Ensuite seulement on laisse passer le flux.

**Critère** : le référent dit **par écrit** dans le canal de la série que le scénario est passé et que les écritures
ne sont pas dupliquées. Sans cet écrit, le lot reste en observation prolongée.

---

## P7 — Observation jusqu'au lendemain

Message J-soir à l'équipe (plan, §9). Tableau de suivi mis à jour : jumeau VM `STOPPED`, GKE `PROD`, réplicas,
heure, validations. Pendant la nuit, personne ne touche à rien. À 9h30, décision : **lot suivant / prolonger /
rollback**. Registre **Services qui restent sur la VM** complété si le lot en a révélé un.

---

## R — Rollback du lot

| | |
|---|---|
| **Quoi** | Ramener le lot à son état d'avant P2, dans l'ordre inverse |
| **Pourquoi l'ordre** | Scaler GKE à 0 **avant** de redémarrer la VM, sinon les deux jumeaux se retrouvent sur la file. Repointer les secrets **en dernier** mais **obligatoirement** : sinon un `rollout restart` ultérieur remettrait les pods sur la prod, des heures après |
| **Où** | Poste (`kubectl-local`) puis VM GPU (`devhp`) puis poste |
| **Durée** | ~1 à 2 minutes. Mesuré le 17/09 sur la flotte entière : 51 s pour le scale, 7 s de reconnexion par conteneur |
| **Décision** | DSO + LEAD, CTO informé. Consigné dans le tableau de suivi, section Rollbacks |

```bash
# R.1 — poste : libérer les files, et ATTENDRE la disparition des pods (SIGTERM ignoré = 30 s de grâce)
while read -r D; do kubectl scale deploy/"$D" --replicas=0 -n "$NS"; done < /tmp/${LOT}-deploys.txt
while read -r D; do kubectl wait --for=delete pod -l app="$D" -n "$NS" --timeout=60s; done < /tmp/${LOT}-deploys.txt   # sinon 2 flottes sur la file pendant ~20 s (L2, 21/09)

# R.2 — VM GPU : la flotte VM se réabonne — MÊME fichier que P2, symétrique exact
xargs -a /tmp/${LOT}-vm-containers.txt docker start

# R.3 — poste : preuve que la prod est reprise
kubectl exec -n rabbitmq-v3 "$POD" -- rabbitmqctl list_queues -q name messages consumers \
  | grep -Ff /tmp/${LOT}-queues.txt | grep -v '_dlq'   # sortie rabbitmqctl séparée par TABULATIONS : ne jamais grep un nom suivi d'un espace          # consumers >= 1 partout

# R.4 — poste : repointer les secrets vers le broker DEV (valeur depuis Secret Manager, même boucle qu'en P3)
# puis remettre replicas=1 pour retrouver l'état shadow
```

**Critère** : `consumers ≥ 1` sur toutes les queues du lot, jumeaux VM `Up`, secrets sur l'hôte dev `10.0.1.217`,
GKE de retour en shadow. Tableau de suivi : jumeau VM `UP`, GKE `shadow`, ligne Rollbacks remplie.

**Après un rollback** : pause d'un jour ouvré, analyse de cause écrite, correction de la procédure. Deux rollbacks
dans la série → suspension et comité.

---

## Ce que le développeur voit passer

Pendant la fenêtre de son lot, entre 14h00 et 16h00, le dev référent est joignable. À ~15h on lui demande de jouer
son scénario métier et de confirmer les écritures. Le soir il reçoit le message J-soir. Le lendemain matin, la
décision. **C'est tout** : aucune commande, aucun accès à l'infrastructure, aucune modification de code pendant la
fenêtre.
