# Rapatriement `features/poc` → `prod` avant les bascules de la vague 2 — information aux devs

> **Décision du 02/10** : le rapatriement est **assuré par le DSO** (PR `poc` → `prod`, code fonctionnel uniquement), pour garantir que tout est fait. Les devs sont **informés** et répondent à une seule question.
> **Destinataires** : LEAD, Rindra (detection-langue, content-extractor, `common_utils`). **Envoi** : vendredi 2/10.
> Contexte : [`plan-vague-2.md`](plan-vague-2.md) § 7ter (exposition) et § 7quater (rapatriement).

---

**Objet : Vague 2 — remonter vers `prod` les correctifs déployés sur la VM via `features/poc` (detection-langue, content-extractor en premier)**

Bonjour,

Lundi 5/10, nous commençons à faire passer les routes de la gateway vers les services Cloud Run. Ces services sont construits depuis la branche **`prod`**, alors que la VM fait tourner le code de **`features/poc`**. En comparant fichier par fichier ce qui tourne sur la VM et ce qu'il y a dans `prod`, nous avons trouvé des correctifs présents **uniquement** dans `poc` :

| Service | Fichiers (dans `poc`, absents de `prod`) | Commits |
|---|---|---|
| `api-detection-langue-fr` | `app/services/scraper.py`, `tests/test_await_or_raise.py` | `341958459`, `228ccd82d` (24/09 — fuite du pool de navigateurs, correctif PROD) |
| `content-extractor-api-service` | `app/core/config.py` (`RESULT_CACHE_VERSION` v2), `tests/test_config.py` | `f13566d7f` (30/09) |
| `libs/common-utils` | `src/common_utils/extractor/HeaderFooterExtractor.py`, `src/common_utils/redis/cache_service.py` + leurs tests | `ac32b0528` (30/09) et précédents |

Si nous basculions sans eux, Cloud Run ferait tourner l'**ancienne** version — pour detection-langue, cela réintroduirait la panne du 24/09.

**Ce que nous faisons** : le DevSecOps ouvre lui-même une PR vers `prod` par service, avec **uniquement le code fonctionnel** listé ci-dessus (+ tests), en gardant les `requirements.txt` et `Dockerfile` de `prod` (épinglés et durcis). Les PR portent aussi les réglages Cloud Run des services (entrée interne, `min_instances`, cache Redis). Merci de **relire** la PR qui vous concerne si vous le pouvez ; un dev par service reste disponible lundi pour tester le parcours réel juste après la bascule.

**Question à Rindra** : le correctif `common_utils` du 30/09 (`HeaderFooterExtractor`) concerne-t-il aussi `website-processor-service` ? Ce consumer tourne sur GKE depuis le 24/09 avec la version de `prod` ; si le correctif le concerne, il faudra le redéployer après le rapatriement.

**Nouvelle règle à partir de maintenant** : pour un service **déjà basculé** (les consumers L1→L6, puis chaque service de la vague 2 au fil des bascules), **les correctifs passent par une PR vers `prod`**, plus par `poc` → VM : la VM ne sert plus ce service. La liste à jour est dans `suivi-bascule-par-lots.md` et `suivi-vague-2.md`.

Pour les sous-vagues suivantes (MCP semrush, gateway, fronts, crawler), nous ferons de même et vous préviendrons quelques jours avant, avec la liste des fichiers concernés.

Merci,
L'équipe DevSecOps
