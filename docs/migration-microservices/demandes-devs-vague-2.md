# Demandes aux devs et à l'équipe — vague 2

> Registre des questions posées aux développeurs, au LEAD et au chef de projet IA pendant la vague 2 : ce qui a été demandé, à qui, pour quand, où en est la réponse et ce qu'elle déclenche.
> Tenu par l'équipe DevSecOps. Mis à jour à chaque envoi, relance ou réponse. Le contexte détaillé reste dans les documents cités.
> Créé le 19/10/2026. Documents liés : [`suivi-vague-2.md`](suivi-vague-2.md), [`reports-et-decisions-vague-2.md`](reports-et-decisions-vague-2.md), [note de décision sur la recherche](rapports/decision-retour-vm-api-recherche-2026-10-15.md).

## Comment lire ce document

| État | Signification |
|---|---|
| 📝 Prêt | message rédigé, pas encore envoyé |
| 📤 Envoyé | message parti, réponse attendue |
| 🔄 En analyse | l'équipe a accusé réception et étudie la question |
| ◐ Répondu en partie | réponse reçue sur une partie des questions ; le reste est relancé |
| ✅ Répondu | réponse reçue et consignée ; la suite est indiquée |
| ⚪ Sans objet | question devenue inutile (décision ou découverte entre-temps) |

Une relance se note dans la colonne « Suivi » avec sa date. Une réponse reçue passe la ligne en ✅ et sa conséquence entre au suivi de la vague.

## 1. Demandes ouvertes

| ID | Date | À qui | Sujet | Questions | Échéance | État | Suivi |
|---|---|---|---|---|---|---|---|
| **D-01** | 15/10 | devs du back-office (PHP, Ecritel) | Recherche : qui envoie les requêtes de nuit | 1. Quel script ou composant appelle `POST /search-service/search` la nuit (20h-03h UTC) ? Piste au 16/10 : le moteur de recherche principal du site<br>2. Que contiennent les requêtes d'environ 20 Ko : valeurs de `top_k`, `ponderation`, sources, `use_reranker` ?<br>3. Délai d'attente côté PHP (mesuré depuis : **60 s**) et relance après un abandon ?<br>4. Ajouter un `User-Agent` qui nomme l'appelant (ex. `hp-bo/<tâche>`) | 19/10 midi | ◐ Répondu en partie (21/10) | 16/10 : questions 2 et 3 complétées après les mesures. **21/10, réponse** : en plus du moteur de recherche du site, **les traitements de classification appellent eux aussi `/search-service/search`** (recherche dans Milvus, avec reranking). Les requêtes de ~20 Ko de nuit sont donc en bonne partie de la classification. Restent sans réponse : contenu exact (`top_k`, `ponderation`, `use_reranker`), relance après abandon à 60 s, `User-Agent` → relancés dans D-06 |
| **D-03** | 16/10 | équipe RAG (`reranking-model-service`) | Reranking : priorité et mémoire GPU | 1. Ajouter des **files de priorité** au reranking, sur le modèle de l'embedding (recherche = haute, classification = moyenne) ? Estimation de charge<br>2. Fixer un `max_length` (512 ?) à la tokenisation et des lots plus petits que 256 ? Validation de la qualité du classement | 19/10 midi | ◐ Répondu en partie (21/10) | 19/10 : la mesure de 24 h confirme l'attente en file (voir § 3). **21/10, réponse** : « c'est la classification qui [passe] en moyenne pour l'instant » — la classification a aujourd'hui la priorité **moyenne** (côté embedding). Pas de réponse sur les **files de priorité du reranking** ni sur le **`max_length`** → relancés dans D-06 |
| **D-04** | 16/10 | devs du back-office | Lots de classification de nuit | 1. Quelle tâche envoie les ~54 lots `POST /classification-service/classification/classify/batch` de 20h à 01h UTC (120 à 708 Ko, 6 à 31 min chacun) ?<br>2. Peut-on **réduire leur taille** (ex. 50 Ko), **les espacer**, ou **les décaler après 01h UTC** ?<br>3. Même `User-Agent` nommé que D-01 | 19/10 midi | ✅ Répondu (21/10) | **21/10, réponse** : **la taille ne peut pas être réduite** (ce sont des fichiers produits) ; **plus de 300 lots chaque nuit**, pour classifier les produits venant des services **scraping-embedding** et du **BO Ecritel**. ⚠️ Écart avec nos mesures : nginx ne voit que 32 à 54 lots par nuit → comptage sur les 10 répliques en cours (`classification_lots_nuit.sh`) ; étalement ou décalage non répondu → D-06 |
| **D-05** | 19/10 | équipe RAG et chef de projet IA | Validation du pont « Triton sur les 2 GPU » | 1. GO pour rendre les 2 GPU visibles à Triton (`docker-compose.yml`, service `triton-server` : `count: all` au lieu de `device_ids: ["1"]`) **jusqu'au retour de vLLM** ? Les modèles sont déjà configurés pour une instance par GPU visible<br>2. Fenêtre souhaitée (jour, hors 20h-01h UTC) et personne qui vérifie la recherche et la classification après le redémarrage de Triton (~1 à 4 min de chargement des modèles)<br>3. Date prévue du retour de vLLM sur le GPU 0, pour planifier le retour arrière | 21/10 | ◐ Répondu en partie (21/10) | décision user 19/10 : application seulement après GO dev. **21/10, réponse** : « à voir » — **le GPU 0 sert aussi à des lancements manuels des services d'OCR (DeepSeek OCR)**. Notre mesure du 16-17/10 l'a vu vide sur 24 h, mais un pont permanent entrerait en conflit avec ces lancements. **Pas de GO** → pont mis en attente ; alternatives sans GPU 0 dans D-06 |
| **D-06** | 21/10 | équipe RAG, back-office, chef de projet IA | Relance consolidée après les réponses du 21/10 | 1. **Reranking** : files de priorité (recherche du site = haute, classification = moyenne) et **`max_length` 512** à la tokenisation. Avec des requêtes de ~20 Ko tronquées seulement à la longueur maximale du modèle, c'est le levier le plus fort sans toucher aux GPU (calcul et mémoire bien plus faibles par paire)<br>2. **Lots** : nous comptons **119 appels `classify/batch` la nuit du 20 au 21/10** (20h-01h UTC), **tous via `api.hellopro.eu`** (aucun appel direct des services scraping-embedding) ; que recouvrent les « plus de 300 lots » : produits, fichiers, ou autre chose ?<br>3. **Classification qui appelle la recherche** : peut-elle passer `use_reranker=false`, ou un `top_k` plus bas, pour ses recherches internes ?<br>4. **OCR sur le GPU 0** : fréquence et horaires des lancements manuels ; un usage du GPU 0 par Triton **la nuit seulement** est-il envisageable ?<br>5. `User-Agent` nommé (D-01) | 23/10 | ✅ Répondu (06/11) | remplace les questions restées ouvertes dans D-01, D-03, D-04 et D-05 ; question 2 ajustée le 21/10 avec le comptage sur les 10 répliques. **Réponse (reçue entre le 21/10 et le 06/11)** : observations et constats partagés, **aucune possibilité de changer ou d'ajuster pour l'instant** → V2-a3-bis suspendu, migration en pause (06/11) (`classification-lots-nuit-1021-0859.log`) |

## 2. Demandes closes

> **06/11** : avec la pause de la migration, aucune demande n'est en attente de réponse. D-01, D-03 et D-05 restent ◐ (questions de fond sans suite possible à court terme) ; elles seront reposées à la reprise, avec les chiffres du § 3.

| ID | Date | À qui | Sujet | Réponse | Conséquence |
|---|---|---|---|---|---|
| **D-02** | 16/10 | chef de projet IA | GPU 0 de la VM inutilisé | **16/10** : vLLM et d'autres modèles reviendront sur le GPU 0 à court et moyen terme | ✅ on garde les 2 L4 ; F-HP-FINOPS-003 devient un plan de capacité GPU. La question du passage à une VM avec une seule L4 est ⚪ sans objet |
| **D-00a** | 13-14/10 | dev de mcp-gateway | Droits Google Search Console (V2-b) | **14/10** : rien à faire, utiliser `https://www.hellopro.fr/` comme `site_url` | ✅ clos (registre § 4) |
| **D-00b** | 13/10 | dev de mcp-gateway | Ringover : `/admin/users` en `403` (V2-b) | **13/10** : probablement voulu (clé API sans droit « utilisateurs ») | ✅ clos ; droit à ajouter seulement si les jetons Ringover à périmètre doivent servir |

## 3. Éléments à transmettre avec les relances

**D-01, D-03 et D-04 — mesure GPU / Triton du 16/10 06:58 au 17/10 06:58 UTC** (`data/cutover/gpu-observe-report-1019-0917.log`) :

| Heure UTC | GPU 1 (Triton) | `bge-reranker` : attente en file / calcul par inférence | `camembert-embedding` : attente / calcul |
|---|---|---|---|
| jour (07h-19h) | 0 à 15 % | 10 ms à 1,6 s / 0,3 à 1,2 s | 5 à 70 ms / 0,03 à 1,3 s |
| **20h-01h** | **92 à 98 %** | **430 à 547 s** / 1,5 à 1,7 s | 0,35 à 0,5 s / 1,8 à 2,2 s |
| 01h-06h | 31 à 81 % | 64 à 143 s / 1,1 à 1,5 s | 0,06 à 0,3 s / 0,3 à 1,4 s |

Le GPU 0 reste à 0 Mio de mémoire toute la journée. En clair : la nuit, une requête de reranking attend en moyenne **7 à 9 minutes** avant d'être calculée, alors que le calcul lui-même dure moins de 2 secondes. L'embedding, qui a des files de priorité, n'attend que quelques centaines de millisecondes.

## 4. Demandes historiques de la vague 2

Les demandes antérieures au 13/10 (validations des devs testeurs, pré-contrôles de lot, confirmation de version de la gateway par le LEAD pour V2-c) sont tracées dans [`suivi-vague-2.md`](suivi-vague-2.md) et dans les fiches [`lots/`](lots/). La confirmation de version de la gateway (V2-c, étape c.1) est ⚪ sans objet depuis la décision du 15/10 (option B : pas de bascule V2-c).

## 5. Analyse des réponses du 21/10

- **La recherche de nuit est en grande partie de la classification** (D-01) : la classification appelle `/search-service/search` avec reranking. Ce n'est donc pas « la classification contre la recherche du site », mais une charge de classification qui passe à la fois par `classify/batch` et par la recherche, et qui noie les recherches interactives.
- **La taille des lots ne bougera pas** (D-04) : ce sont des fichiers produits. Le levier passe donc par le **coût par paire** du reranking (`max_length`) et par la **priorité** des appels interactifs.
- **Le GPU 0 n'est pas libre en permanence** (D-05) : lancements manuels de DeepSeek OCR. Le pont permanent est écarté ; un usage la nuit seulement reste à discuter.
- **Écart à vérifier** (D-04) : « plus de 300 lots par nuit » contre 32 à 54 vus par nginx. Soit d'autres appelants passent hors de la gateway, soit « lot » ne désigne pas la même chose. Le comptage sur les 10 répliques tranche. **Résultat (21/10)** : 119 lots la nuit du 20 au 21/10, tous via la gateway → personne ne contourne nginx ; l'écart tient à l'unité comptée.
