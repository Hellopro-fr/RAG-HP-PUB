# MCP HelloData — compte rendu des préconditions

- **Plan** : `docs/superpowers/plans/2026-09-21-mcp-hellodata-selection.md` (Task 0)
- **Spec** : `docs/superpowers/specs/2026-09-21-mcp-hellodata-selection-design.md` (§ 12)
- **Ouvert le** : 2026-09-21
- **Environnement de vérification** : BO de dev, `https://dev-bo.hellopro.fr`,
  écriture par `sftp-mcp/dev-write-prod`, lecture par `sftp-mcp/dev-read-prod`

Une ligne par précondition : la question, l'observation, la valeur retenue.
Une précondition non résolue reste **ouverte**, elle n'est pas contournée.

## Bloquants encore ouverts

| # | Question | Pourquoi ça bloque |
|---|---|---|
| 1 | Jusqu'où Ecritel laisse-t-il courir une réponse HTTP ? | Un flux coupé livrerait un CSV tronqué sans erreur visible |
| 4 | Le wrapper joint-il le BO depuis son hôte ? | Sans ce chemin réseau, l'architecture ne tient pas |
| 6 | Coût réel des sous-requêtes corrélées | Décide si la règle de composition § 4.3.3 est tenable |
| 7 | Isolation du port 8597 en production | C'est **la** garantie du modèle d'accès |
| 8 | Où injecter les variables d'environnement | Le dépôt est public, aucune adresse ne doit y transiter |

## Détail

### 1. Chemin hors racine web — **QUESTION REMPLACÉE**

**Résolu par un changement de design**, pas par une réponse : l'export ne
produit plus de fichier (§ 13 de la spec). Le CSV est streamé à la demande,
rien ne reste au repos sur le BO, et le cache de comptage vit dans
`sys_get_temp_dir()`, hors racine web par nature.

**La nouvelle question, qui hérite du caractère bloquant** : jusqu'où
Ecritel laisse-t-il courir une réponse HTTP ? `max_execution_time`,
`mod_fcgid`, timeouts de proxy. Un flux coupé au milieu livrerait un CSV
**tronqué sans erreur visible** — d'où la ligne sentinelle `# fin-export;<n>`
que le wrapper doit vérifier.

**Observation qui a mené là** (conservée pour mémoire)

**Observation.** Le listage de `/` sur `dev-read-prod` rend des fichiers
servis par le web : `maj_prod_bureaustore.php`,
`redirection_lien_acheteur.php`, `test_serveur.php`, et les répertoires
`mon_compte_acheteur/`, `comptabilite/`, `images_cmp/`.

Recoupement avec la source de production : `lancer_comptage_combine.php`
fait `require_once($_SERVER['DOCUMENT_ROOT']."admin/secure/check_session.php")`,
donc `DOCUMENT_ROOT` se termine par `/` et `/admin` est directement dessous.

**Conclusion : la racine SFTP `/` est le `DOCUMENT_ROOT`.** Aucun
répertoire hors racine web n'est accessible par ce compte.

**Test du repli `.htaccess` : armé, non mené à terme.** Un témoin **non
protégé** déposé à `/admin/mcp/hellodata/temoin_public.txt` a répondu
**200**, ce qui prouve que le chemin est servi et donc que le test aurait
été concluant. Il s'est arrêté là : le MCP `sftp-reader` refuse d'écrire un
`.htaccess` (motif de son `.sftpignore`, avec `*.env`, `*.key`, `*.pem`,
`id_rsa`, `/secure`, `/log`), et cette garde n'a pas été levée.

**Décision prise** : ne pas dépendre d'un `.htaccess`, dont l'échec sous
`AllowOverride None` serait muet. L'export passe en flux (§ 13 de la spec).

**Nettoyage effectué et vérifié** : les deux témoins et le répertoire
`var/` ont été supprimés, et les deux URL répondent désormais `404`.

### 2. Version de PHP sur Ecritel — **ouvert**

Non observée. Le plan écrit du PHP compatible **7.0+** : pas de types de
propriété, pas d'opérateur `?->`, pas d'arguments nommés. À confirmer avant
le premier déploiement ; si Ecritel est en 5.x, plusieurs constructions
devront changer.

### 3. `.htaccess` imposant une session sur `/admin/` — **RÉSOLU, pas de blocage**

```
curl -o /dev/null -w '%{http_code}' https://dev-bo.hellopro.fr/admin/   → 200
```

`/admin/` répond **200 sans en-tête d'authentification**. Il n'y a donc pas
d'authentification HTTP au niveau du répertoire ; la protection du BO se
fait bien fichier par fichier, via `require_once .../check_session.php` en
tête de chaque `.php`.

**Conséquence pour le design** : le moteur peut vivre sous `/admin/` et
répondre à un simple Bearer, sans être intercepté. C'est ce que la spec
supposait, et c'est vérifié.

**Conséquence inverse, à ne pas perdre de vue** : c'est exactement pour
cette raison qu'un `.csv` déposé sous `/admin/` serait servi sans aucune
authentification. La précondition 1 en découle directement.

### 4. Joignabilité réseau RAG → BO — **partiellement résolu, reste bloquant**

Depuis **la machine de développement**, `https://dev-bo.hellopro.fr` répond
(`/` → 302, `/admin/` → 200).

**Ce n'est pas la question posée.** Il reste à vérifier depuis **l'hôte qui
exécutera `mcp-hellodata-service`**, qui n'est pas cette machine. Tant que
ce n'est pas fait, la précondition reste ouverte.

### 5. Droit aux colonnes téléphone et e-mail — **ouvert, décision métier**

Question : un utilisateur admis **par la liste statique** (donc non `admin`)
a-t-il droit à `email` et `mobile` ?

**Défaut appliqué en attendant** : non. Seul un `admin` les obtient
(`acces.EstAdmin` côté wrapper, `colonnes_restreintes_autorisees` côté
moteur). C'est le choix prudent ; il se relâche par une ligne si la réponse
est l'inverse.

### 6. Coût réel des sous-requêtes corrélées — **ouvert, bloquant pour A4**

Non mesuré. Tant que ce n'est pas fait, la règle de composition du § 4.3.3
— toute feuille est un prédicat autonome — est un pari, pas un fait.

Repli documenté si le coût est prohibitif : restreindre les critères sur
tables liées à la chaîne `ET` de premier niveau, et l'annoncer au LLM dans
le message de refus.

### 7. Isolation réseau du service en production — **ouvert, bloquant pour la mise en service**

Non vérifiable tant que le service n'est pas déployé. À rejouer sur le
déploiement réel, pas seulement dans `docker-compose.yml` : si autre chose
que le gateway peut joindre le port 8597, `X-End-User-Role: admin` est
forgeable et la liste d'autorisés ne protège rien.

### 8. Où injecter les variables d'environnement — **ouvert, bloquant**

Deux jeux distincts :

- côté Ecritel : `MCP_HELLODATA_TOKEN` seule, lue par `getenv()` dans le
  moteur. `MCP_HELLODATA_VAR` **a disparu** avec le passage à l'export en
  flux : il n'y a plus de répertoire d'état. Le mécanisme d'injection
  dépend de l'hébergement — `SetEnv`, configuration PHP-FPM, ou un include
  maison. À observer sur place.
- côté RAG : `HELLODATA_ALLOWED_EMAILS`, qui contient des adresses
  d'employés. Le dépôt étant **public**, elle ne doit transiter par aucun
  fichier tracké, y compris un `.env.example`.

### 9. Budget du live-fetch `tools/list` — **ouvert**

À relire dans `scoped_gateway.go:363` et à confirmer : un backend lent ne
doit pas pénaliser le `tools/list` des autres backends agrégés dans la même
réponse.

### 11. Schéma réel de `acheteur` — **partiellement résolu**

**Découverte.** `bdd_describe_table` ne rend **pas** le schéma réel mais le
registre curé `bdd_used_fields`. Il annonce 29 colonnes ; la table en a
davantage.

Preuves, obtenues par `bdd_query_readonly` — une colonne valide rend zéro
ligne, une colonne inexistante rend une erreur :

| Colonne | Listée par `describe` | Existe réellement |
|---|---|---|
| `bloquage_a` | non | **oui** — `COUNT(*) WHERE bloquage_a = 0` rend 5 615 366 |
| `email_a` | non | **oui** — zéro ligne, sans erreur |
| `mail_a` | non | **non** — erreur base de données |
| `telephone_a` ou `effectif_a` | non | **au moins un des deux n'existe pas** |

**Colonnes confirmées**, utilisables sans nouvelle vérification :

`id_acheteur`, `id_source_a`, `source_a`, `date_creation_a`,
`raison_sociale_a`, `nom_commercial_a`, `cp_a`, `ville_a`, `adresse_a`,
`site_web_a`, `civilite_a`, `nom_a`, `prenom_a`, `code_fonction_a`,
`code_service_a`, `statut_a`, `telephone_mobile_a`, `siret_a`, `siren_a`,
`code_effectif_a`, `code_naf_a`, `naf_niv2_a`, `naf_niv3_a`, `naf_niv4_a`,
`id_pays_a`, `departement_a`, `region_a`, `annee_creat_a`, `mois_creat_a`,
`bloquage_a`, `email_a`

**Reste ouvert** : un `DESCRIBE acheteur` authentique, et le schéma des
tables liées dont dépendent les critères DI et emailing. Sans lui, le plan
livre **23 critères** au lieu des 46 champs annoncés par la spec — écart
documenté, pas oublié.

**Clé de jointure DI déjà connue**, lue dans
`lancer_comptage_combine.php` : `DI.id_societe = A.id_source_a`.

## Environnement local

`go` et `php` ne sont **pas installés** sur la machine de développement.
Seul Docker l'est (`docker compose` 2.40.3). Toutes les commandes de test
du plan passent donc par un conteneur jetable.
