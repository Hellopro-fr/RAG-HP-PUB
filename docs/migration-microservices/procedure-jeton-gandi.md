# Procédure — jeton d'accès Gandi temporaire pour la vague 2

> **Pour qui** : le titulaire du compte Gandi de l'organisation Hellopro (création du jeton), puis le DSO (stockage, usage, révocation).
> **Pourquoi** : décision 9 de la vague 2 (30/09) — toutes les modifications DNS de la vague passent par des scripts relus
> (lecture de la valeur actuelle, écriture, relecture, journal) plutôt que par des clics dans l'interface.
> Suivi : [`suivi-vague-2.md`](suivi-vague-2.md), action 0.12 · plan : [`plan-vague-2.md`](plan-vague-2.md) § 5.

---

## 1. Ce que le jeton doit permettre — et rien de plus

| Réglage | Valeur à choisir | Pourquoi |
|---|---|---|
| Type | **Jeton d'accès personnel** (Personal Access Token), pas une ancienne « clé API » | les jetons ont une expiration et un périmètre ; les clés API sont dépréciées |
| Organisation | l'organisation Hellopro qui détient `hellopro.eu` | |
| Nom | `vague2-dns-dso-2026-10` | retrouver et révoquer le bon jeton |
| Expiration | la plus proche du **23/10/2026** proposée par l'interface (pas « jamais ») | fin prévue de la vague 2 ; un jeton oublié expire seul |
| Ressources | **le domaine `hellopro.eu` seul** — ne pas cocher « tous les domaines », ni `hellopro.fr` | toutes les adresses de la vague sont en `.hellopro.eu` (y compris `nextjs-conseils.hellopro.eu`, derrière `conseils.hellopro.fr`) |
| Droits | **uniquement la gestion de la configuration technique / DNS** du domaine (intitulé indicatif : « Gérer la configuration technique des domaines ») | ni facturation, ni renouvellement, ni transfert, ni gestion de l'organisation |

Les intitulés exacts de l'interface Gandi peuvent varier : en cas de doute sur un droit, **ne pas le cocher** — le test du § 4 dira s'il manque quelque chose.

---

## 2. Création (titulaire du compte Gandi, ~5 minutes)

1. Se connecter à l'interface d'administration Gandi avec le compte titulaire.
2. Ouvrir les **paramètres de l'utilisateur** (menu du compte, en haut à droite), puis la rubrique des **jetons d'accès personnel**.
3. **Créer un jeton** et renseigner les réglages du § 1 (organisation, nom, expiration, ressource `hellopro.eu`, droits DNS seuls).
4. Valider. Le jeton s'affiche **une seule fois**.
5. **Ne pas** l'envoyer par e-mail, chat, ticket ni capture d'écran. Le passer directement au § 3 (de préférence en étant à côté du DSO, ou en le saisissant soi-même dans la commande du § 3).

Si le jeton est perdu avant le § 3 : le supprimer dans Gandi et en créer un autre.

---

## 3. Stockage dans Secret Manager (DSO ou titulaire, poste Git Bash)

Le jeton n'apparaît ni à l'écran, ni dans l'historique, ni dans un fichier : il est saisi en mode masqué puis envoyé directement à Secret Manager.

```bash
gcloud config configurations activate default
read -rs -p "Coller le jeton Gandi puis Entree : " T; echo
printf '%s' "$T" | gcloud secrets create gandi-livedns-pat --project hellopro-rag-project \
  --replication-policy=automatic --labels=owner=devsecops,usage=vague2-dns,expire=2026-10-23 --data-file=-
unset T
gcloud secrets versions list gandi-livedns-pat --project hellopro-rag-project --format='value(name,state,createTime)'
gcloud config configurations activate kubectl-local
```

Attendu : une version `1` à l'état `ENABLED`. Si le secret existe déjà (nouveau jeton), remplacer `gcloud secrets create … --replication-policy=automatic --labels=…` par `gcloud secrets versions add gandi-livedns-pat --project hellopro-rag-project --data-file=-`.

---

## 4. Vérification du périmètre (DSO, lecture seule)

```bash
gcloud config configurations activate default
HF=$(mktemp); chmod 600 "$HF"   # en-tete dans un fichier 600 : le jeton n'apparait pas dans la liste des processus
printf 'Authorization: Bearer %s' "$(gcloud secrets versions access latest --secret=gandi-livedns-pat --project hellopro-rag-project)" > "$HF"
G() { curl -s -o /dev/null -w '%{http_code}' -H @"$HF" "https://api.gandi.net/v5/livedns/domains/$1"; }
echo "hellopro.eu (attendu 200)              : $(G hellopro.eu)"
echo "enregistrement A de rag (attendu 200)  : $(G hellopro.eu/records/rag/A)"
echo "hellopro.fr (attendu 403 ou 404)       : $(G hellopro.fr)"
rm -f "$HF"; unset HF
gcloud config configurations activate kubectl-local
```

| Résultat | Lecture |
|---|---|
| `200` / `200` / `403` ou `404` | ✅ jeton valide et **limité à `hellopro.eu`** |
| `hellopro.fr` en `200` | ❌ périmètre trop large : supprimer le jeton dans Gandi, en recréer un restreint, remplacer la version du secret |
| `401` | jeton invalide ou mal collé : recommencer le § 3 avec `versions add` |
| `403` sur `hellopro.eu` | droit DNS manquant : recréer le jeton avec le droit de configuration technique |

---

## 5. Usage pendant la vague

Toute modification passe par un script qui, pour un enregistrement : **lit** la valeur actuelle et la consigne dans le journal Gandi de [`suivi-vague-2.md`](suivi-vague-2.md) § 4 (= valeur de retour arrière), **écrit** la nouvelle valeur, **relit** et compare. Le jeton n'est lu qu'au moment de l'appel (`gcloud secrets versions access`), jamais stocké dans un fichier ni affiché. Les scripts sont versionnés dans `RAG-HP-PUB-infra/infra-microservices/scripts/migration/vague2/`.

| Quand | Modification |
|---|---|
| dès réception du jeton | CNAME `_acme-challenge.<hôte>` de validation des certificats (valeurs fournies par Certificate Manager) |
| dès réception du jeton | TTL des 6 adresses de la vague → 300 s (valeur inchangée) — au moins 48 h avant la première bascule DNS |
| jour de chaque bascule V2-c / V2-d | A de l'adresse : `35.245.31.1` → IP du load balancer |
| fin de vague | TTL remontés à 3600 s |

---

## 6. Révocation (fin de vague, ou au moindre doute)

1. **Gandi** (titulaire) : supprimer le jeton `vague2-dns-dso-2026-10` dans la rubrique des jetons d'accès personnel.
2. **Secret Manager** (DSO) : `gcloud secrets versions disable 1 --secret=gandi-livedns-pat --project hellopro-rag-project`, puis suppression du secret une fois la vague close.
3. Noter la révocation dans le journal de [`suivi-vague-2.md`](suivi-vague-2.md).

**En cas de fuite suspectée** (jeton affiché, collé au mauvais endroit) : révoquer immédiatement dans Gandi, puis vérifier dans l'interface Gandi que les enregistrements de `hellopro.eu` n'ont pas changé.
