# MCP HelloData — accès par `server_authorizations` et masquage OAuth2

**Date :** 2026-09-28
**Branche :** `features/mcp-bdd-table`
**Statut :** implémenté le 2026-10-04, avec l'amendement ci-dessous
**Remplace :** D10, D11 et § 7.1 de `2026-09-21-mcp-hellodata-selection-design.md`

> **Amendement du 2026-10-04 — réutilisation de `Neo4jAccess`.** Entre la
> rédaction et l'implémentation, `features/poc` a reçu #832
> (`internal/gateway/neo4j_access.go`), qui applique déjà la règle A2
> (admin OU grant, admin vérifié d'abord, fail-closed) aux trois points du
> § 3 — consentement HTML/JSON et soumissions, `tools/list` /
> `resources/list` / `prompts/list`, `tools/call` / `resources/read` /
> `prompts/get`. HelloData est le « deuxième service » qu'évoquait le § 2,
> et la branche a d'abord été fusionnée avec poc. Écarts au texte qui suit :
>
> - **§ 4.1 à 4.4 :** pas de `HellodataAllows` ni de
>   `FilterHellodataServers`. `Neo4jAccess` tient un serveur pour
>   restreint aussi quand son `tool_prefix` vaut `hellodata` (en mémoire
>   pour un backend du registre ; relu en base par
>   `ServerRepo.AccessKeysByID` quand on n'a que l'id, au consentement).
>   Une erreur de lecture rend le serveur restreint. Le refus de
>   `tools/call` utilise le message existant
>   `access denied: this server requires an admin role or a server authorization`
>   (JSON-RPC `-32600`).
> - **§ 4.6 :** les refus sont journalisés par le préfixe `[neo4j-access]`
>   existant (backend, slug, e-mail), sans les codes de raison du § 4.6.
> - **Défaut trouvé à l'implémentation :** le registre ne contient jamais
>   d'outil hellodata (la découverte interroge le wrapper sans identité et
>   reçoit `[]`), donc `tools/call` renvoyait `unknown tool` à tout le monde,
>   admin compris. `handleToolsCall` route désormais un nom `hellodata_*`
>   absent du registre vers le backend hellodata du scope
>   (`findHellodataFallback`), avant le repli Zoho ; `min_role` et le
>   contrôle d'accès s'appliquent ensuite.
> - **A6 — valeur de `min_role` :** les rôles du gateway s'écrivent
>   `config-only` < `read-only` < `admin` (`internal/auth/role.go`).
>   `readonly` sans tiret n'est pas un rôle : `GateAllowsEmail` refuse
>   alors tout le monde, admins compris. `read-only` écarterait les
>   titulaires de grant au rôle `config-only`, rôle par défaut de
>   `users/sync`. Valeur retenue : **`min_role = config-only`**, qui écarte
>   toujours les chemins sans e-mail.
> - **§ 4.5 et § 5 :** implémentés tels quels. Le proxy `/download` lit les
>   en-têtes par le même `transport.IdentiteDepuis` que `/mcp`.

Ce document est le **sous-projet 1** de la fonctionnalité « campagnes
acheteurs via Claude ». Le sous-projet 2 (tables d'historique, sélection
croisée avec l'historique, webhook front) a sa propre spec. Le présent
sous-projet se livre seul : il ne dépend d'aucune table nouvelle.

---

## 1. Contexte

### 1.1 Ce qui existe

`mcp-hellodata-service` (Go, port 8597) expose trois outils — `compter`,
`echantillon`, `export_csv` — derrière `mcp-gateway-service`. L'accès est
décidé **dans le wrapper** (`internal/acces/acces.go`) : rôle `admin`, ou
adresse présente dans la variable `HELLODATA_ALLOWED_EMAILS`. Le gateway
pose `min_role = readonly` et injecte `X-End-User-Email` /
`X-End-User-Role` (`injectHellodataIdentity`, `scoped_gateway.go`).

La spec du 2026-09-21 assumait ce choix comme provisoire : « le jour où l'un
des deux [redémarrage pour changer la liste, absence d'écran] manque, c'est
le signal qu'il faut une vraie table ». Ce jour est arrivé : les accès
doivent se gérer depuis l'écran `/server-authorizations`, et un utilisateur
non autorisé ne doit **pas voir** le serveur hellodata dans la liste de
l'écran de consentement OAuth2.

### 1.2 Le précédent : Zoho

`server_authorizations` porte déjà deux sens dans le gateway :

| Backends | Sens d'un grant `(server_id, email)` | Où |
|---|---|---|
| leexi, ringover, bdd (backends **filtrés**) | « accès non filtré » : les en-têtes de filtrage ne sont pas injectés | `requestHeadersFor` Step 0, `internal/db/models.go:627` |
| zoho (backend **identifié**) | « droit d'accès » au compte admin Zoho pour un non-admin | `internal/app/zoho_catalog_adapter.go:33,66` |

HelloData est, comme Zoho, un backend identifié : ses en-têtes ne filtrent
pas, ils authentifient. Il prend donc le **second sens**.

### 1.3 Le piège actuel du Step 0

Dans `requestHeadersFor`, un grant déclenche un `return headers` immédiat
(Step 0), **avant** le `switch` qui appelle `injectHellodataIdentity`. Seul
Zoho a une exception qui ré-injecte l'identité. Conséquence aujourd'hui :
créer un grant hellodata pour un utilisateur supprime son
`X-End-User-Email`, et le wrapper le **refuse**. Un grant produit l'effet
inverse de celui voulu. Ce défaut est corrigé ici et verrouillé par un test
de régression.

---

## 2. Décisions

| # | Question | Décision |
|---|---|---|
| A1 | Découpage | Deux sous-projets ; celui-ci (autorisation) d'abord, livrable seul |
| A2 | Règle d'accès | `gateway_users.role == "admin"` **OU** ligne `server_authorizations(server_id = <id du serveur hellodata>, email)` |
| A3 | Lieu de la décision | **Le gateway décide** (consentement, `tools/list`, `tools/call`) ; **le wrapper re-vérifie** en défense sur les en-têtes injectés |
| A4 | Source de vérité | La table `server_authorizations` seule. `HELLODATA_ALLOWED_EMAILS` est **supprimée** |
| A5 | Identification du serveur | Par `tool_prefix == "hellodata"`, comme leexi/ringover/bdd/zoho sont déjà dispatchés. Pas de colonne nouvelle, `GateAllowsEmail` **non modifié** |
| A6 | Première barrière | `min_role = readonly` conservé : il écarte les tokens de scope et `client_credentials`, qui ne portent jamais d'e-mail |
| A7 | Frontend | Aucun changement : `ServerAuthorizationsView.vue` est générique et liste déjà tout serveur de `mcp_servers` |

Écarté :

- **Colonne `mcp_servers.grant_required`** : généralisable, mais migration
  GORM + champ frontend + modification du filtre commun à tous les serveurs,
  pour un seul consommateur. À reconsidérer au deuxième service qui en aurait
  besoin.
- **`min_role = admin` + un grant satisfait le gate** : modifie le prédicat
  fail-closed `GateAllowsEmail` sur ses cinq points d'appel et changerait le
  sens des grants leexi/ringover/bdd existants.
- **Garder la liste statique en plus** : deux sources de vérité ; une adresse
  listée sans grant aurait droit au service sans le voir dans OAuth2.
- **Wrapper aveugle** (aucune re-vérification) : l'isolation réseau
  deviendrait l'unique protection d'un export de coordonnées d'acheteurs.

---

## 3. Vue d'ensemble

```
Écran de consentement OAuth2 ─► gateway : HellodataAllows ? afficher : masquer
tools/list                   ─► gateway : HellodataAllows ? live-fetch wrapper : []
tools/call                   ─► gateway : HellodataAllows ? forward : DENIED
                                   │ X-End-User-Email
                                   │ X-End-User-Role        (fail-closed, inchangé)
                                   │ X-End-User-Granted: true   (nouveau, émis seulement si grant)
                                   ▼
                     mcp-hellodata-service : email != "" && (role == "admin" || granted)
```

---

## 4. Gateway — `mcp-gateway-service`

### 4.1 Le prédicat

Nouveau fichier `internal/gateway/hellodata_access.go` :

```go
// HellodataAllows reports whether email may see and reach the hellodata
// server serverID: gateway role admin, OR an explicit server_authorizations
// grant on that server.
//
// Fail-closed: empty email, unwired finders, lookup error, or no row → false.
func HellodataAllows(serverID, email string, users gatewayUserFinder, grants serverAuthorizer) bool
```

- Fonction **pure** (pas de récepteur), comme `FilterServersByGate`, pour
  rester testable sans plomberie `AuthServer`.
- Le rôle admin se compare à l'égalité stricte (`"admin"`), via
  `gatewayUserRole` existant : un rôle non résolu n'est pas admin.
- `serverAuthorizer` est l'interface déjà définie dans `scoped_gateway.go:27`.
  `ServerAuthorizationRepo.IsAuthorized` renvoie `false` en cas d'erreur, ce
  qui convient au fail-closed.

### 4.2 Écran de consentement (masquage)

Les deux points d'entrée appellent déjà `FilterServersByGate` avant de
construire `serverMap` :

- `internal/authserver/authorize.go:248` (`renderConsent`, HTML)
- `internal/authserver/authorize_api.go:430` (`buildServerList`, JSON)

Juste après, un second filtre pur `FilterHellodataServers(servers, email,
users, grants)` retire tout serveur `tool_prefix == "hellodata"` pour lequel
`HellodataAllows` est faux. Placé avant `serverMap`, il couvre les deux
branches (scope pré-configuré par l'admin, et affichage de tous les
serveurs), exactement comme le filtre `min_role`.

`AuthServer` a besoin du `serverAuthorizer` : il est câblé dans
`internal/app/app.go` à côté de `SetServerAuthorizationRepo` (l.382-385),
le même dépôt que celui du gateway.

### 4.3 `tools/list`

`hellodataBackendsInScope` renvoie les backends hellodata du scope ; pour
chacun, le live-fetch (`fetchHellodataTools`) n'est lancé **que si**
`HellodataAllows` est vrai. Sinon, aucun appel réseau et aucun outil. Le
repli existant sur liste vide en cas d'échec du wrapper est conservé tel
quel (divergence volontaire avec Zoho, documentée dans le code).

### 4.4 `tools/call`

Dans `handleToolsCall`, après le contrôle `GateAllows(min_role)` existant et
avant le forward : si le backend est hellodata et que `HellodataAllows` est
faux, réponse `DENIED` avec le même format d'erreur que le refus `min_role`.

Ce refus n'est pas redondant avec le masquage : un client MCP peut appeler
un nom d'outil qu'il n'a jamais vu listé. Le masquage relève de l'ergonomie,
le refus de la sécurité.

### 4.5 En-têtes — correction du Step 0

Dans `requestHeadersFor`, la branche Step 0 (grant présent) ré-injecte
l'identité pour hellodata, sur le modèle de l'exception Zoho :

```go
if sg.isServerAuthorized(ctx, backend.ID) {
    ...
    if backend.HasTag(zohoToolPrefix) || backend.ToolPrefix == zohoToolPrefix {
        sg.injectZohoIdentity(ctx, headers, backend)
    }
    if backend.ToolPrefix == hellodataToolPrefix {
        sg.injectHellodataIdentity(ctx, headers, true)
    }
    return headers
}
```

`injectHellodataIdentity(ctx, headers, granted bool)` :

- pose `X-End-User-Email` (inchangé) ;
- pose `X-End-User-Role` uniquement si le rôle est résolu (inchangé,
  fail-closed à l'émission) ;
- pose `X-End-User-Granted: true` **uniquement** quand `granted` est vrai.
  Jamais de `false`, jamais de valeur par défaut : côté wrapper, une valeur
  par défaut deviendrait un droit effectif.

Nouvelle constante `EndUserGrantedHeader = "X-End-User-Granted"` à côté de
`EndUserEmailHeader` / `EndUserRoleHeader` (`scoped_gateway.go:60`). Le
chemin hors grant (dans le `switch`) appelle `injectHellodataIdentity(ctx,
headers, false)`.

### 4.6 Journalisation

Chaque refus hellodata est journalisé avec `backend`, `email` et une
raison parmi `no_email`, `role_lookup_failed`, `not_admin_no_grant` — sur
les trois chemins (consentement, `tools/list`, `tools/call`).

Limite connue : `ServerAuthorizationRepo.IsAuthorized` renvoie `false`
aussi bien pour une ligne absente que pour une erreur SQL (le repo avale
l'erreur). Une panne de la table `server_authorizations` apparaît donc
comme `not_admin_no_grant`. C'est sûr (refus), mais pas diagnostiquable
depuis ce journal ; on ne modifie pas le repo, partagé avec les grants
leexi/ringover/bdd/zoho.

---

## 5. Wrapper — `mcp-hellodata-service`

- `transport.IdentiteDepuis` lit en plus `X-End-User-Granted` ; seule la
  valeur exacte `true` compte (`tools.Identite.Granted bool`).
- `acces.Autorise(email, role string, granted bool) bool` :

  ```go
  // Refuse sans identite. Autorise l'admin, ou l'appelant pour qui le
  // gateway a constate un grant server_authorizations.
  if email == "" { return false }
  return role == roleAdmin || granted
  ```

- Suppression de la liste statique : `acces.Nouveau`, le champ
  `config.EmailsAutorises`, la lecture de `HELLODATA_ALLOWED_EMAILS`.
- Journal d'appel accepté : l'adresse (déjà exigée par la spec du
  2026-09-21) **et** la source du droit, `admin` ou `grant`.

La garantie réseau de la spec du 2026-09-21 reste intégralement valable :
`expose:` et jamais `ports:` ; sans elle, `X-End-User-Granted: true` est
aussi forgeable que `X-End-User-Role: admin`.

---

## 6. Comportement attendu

| Appelant | Consentement OAuth2 | `tools/list` | `tools/call` |
|---|---|---|---|
| `admin` | visible | 3 outils (live-fetch) | transmis |
| Grant sur le serveur hellodata | visible | 3 outils | transmis avec `X-End-User-Granted: true` |
| `readonly` sans grant | **masqué** | `[]` | `DENIED` |
| Aucun e-mail (scope token, `client_credentials`) | masqué | `[]` | `DENIED` |
| Erreur SQL `gateway_users` / `server_authorizations` | masqué | `[]` | `DENIED` |
| Wrapper injoignable | selon la règle | `[]` (pas de repli cache) | erreur interne |

Les autres serveurs ne sont pas affectés : un grant leexi/ringover/bdd
continue de retirer leurs en-têtes de filtrage.

---

## 7. Tests

**Gateway** (`go test ./...`, `go vet ./...`) :

1. `HellodataAllows` en table : admin / grant / ni l'un ni l'autre / e-mail
   vide / `users` nil / `grants` nil / erreur de lookup.
2. `FilterHellodataServers` : serveur hellodata masqué ou conservé ; un
   serveur non hellodata jamais retiré.
3. Consentement HTML et JSON : un `readonly` sans grant ne reçoit pas le
   serveur hellodata, y compris quand le client OAuth2 l'a en scope
   pré-configuré.
4. **Régression Step 0** : avec un grant hellodata, `requestHeadersFor`
   contient `X-End-User-Email` **et** `X-End-User-Granted: true`.
5. Sans grant : pas d'en-tête `X-End-User-Granted`.
6. `tools/call` refusé pour un `readonly` sans grant, sans appel au backend.
7. `tools/list` : aucun live-fetch pour un non-autorisé.
8. Non-régression : un grant sur un backend `bdd` retire toujours
   `X-BDD-Allowed-Tables`.

**Wrapper** (`go test ./...`, `go vet ./...`) :

1. `acces_test.go` réécrit : admin / granted / aucun / e-mail vide /
   `granted` sans e-mail refusé.
2. `transport` : `X-End-User-Granted: TRUE`, `1`, `yes` ne valent **pas**
   `true`.
3. `config_test.go` : plus de `HELLODATA_ALLOWED_EMAILS`.
4. `handler_test.go` : `tools/list` vide pour un non-autorisé (inchangé).

---

## 8. Documents à mettre à jour dans le même travail

- `2026-09-21-mcp-hellodata-selection-design.md` : D10, D11 et § 7.1
  annotés « remplacé par `2026-09-28-mcp-hellodata-server-authorizations-design.md` ».
  L'historique n'est pas réécrit.
- `apps-microservices/mcp-hellodata-service/CLAUDE.md` : § Accès, table des
  variables d'environnement, prérequis.
- `apps-microservices/mcp-gateway-service/CLAUDE.md` : les deux sens de
  `server_authorizations` (§ 1.2 ci-dessus).
- `docker-compose.yml` (service `mcp-hellodata-service`, l.2533 et 2546) :
  retrait de la variable et du commentaire qui la cite.
- Le correctif de commentaire non commité dans `scoped_gateway.go`
  (« four tools » → « three tools ») est intégré au même lot.

---

## 9. Livraison

Ordre imposé, sinon les utilisateurs de la liste statique perdent l'accès
pendant la bascule :

1. **Manuel** : pour chaque adresse de la `HELLODATA_ALLOWED_EMAILS` en
   production, créer un grant sur le serveur hellodata depuis
   `/server-authorizations`.
2. Déployer le gateway. Tant que le wrapper n'est pas redéployé, il continue
   d'accepter admin + liste statique ; les granted de l'étape 1 y figurent
   déjà.
3. Déployer le wrapper, puis retirer la variable du `.env` de production.
4. Vérification : un compte `readonly` sans grant ne voit pas hellodata au
   consentement ; le même compte, une fois le grant créé, le voit et obtient
   les trois outils.

---

## 10. Hors périmètre

- Tout le volet campagnes (tables `historique_campagne_*_ia`, outils de
  sélection croisée avec l'historique, webhook
  `partenaires_externes/mcp/hellodata`) : sous-projet 2.
- Généralisation du marquage « admin OU grant » à d'autres serveurs (§ 2).
