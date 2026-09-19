# Procédure de bascule d'un lot — la même pour les sept

> **Exécutée par le DevSecOps**, en présence du référent dev du lot. Les développeurs n'ont **aucune** de ces
> commandes à lancer : ce document est publié pour que chacun sache ce qui se passe, dans quel ordre, et quand
> son tour arrive.
>
> Les commandes ci-dessous sont des **gabarits** (`<LOT>`, `<nom>`). Les cartes d'exécution exactes — quoi, où,
> quand, impact — sont produites au moment de chaque lot, à partir de la fiche `lots/L<n>.md`.
> Aucun secret n'apparaît ici : les valeurs viennent de Secret Manager au moment de l'exécution.

---

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
rollback**.

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
# R.1 — poste : libérer les files
while read -r D; do kubectl scale deploy/"$D" --replicas=0 -n "$NS"; done < /tmp/${LOT}-deploys.txt

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
