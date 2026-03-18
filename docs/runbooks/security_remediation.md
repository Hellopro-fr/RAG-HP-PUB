# Runbook - Remediation Securite Urgences

> **Date**: 2026-03-17 | **Derniere MAJ**: 2026-03-18
> **Criticite**: CRITIQUE → EN COURS DE REMEDIATION
> **Responsable**: DevSecOps
> **Prerequis**: Acces `gcloud` et `kubectl` configures sur le projet `hellopro-rag-project`
> **Cluster GKE**: `matching-api-dev-k8s` (zone: `europe-west1-b`)

## Etat d'avancement des remediations (2026-03-18)

| SEC | Action | Statut | Note |
|-----|--------|--------|------|
| SEC-2 | Supprimer regle RDP | ✅ FAIT | Regle etait deja desactivee+restreinte. Supprimee le 2026-03-18. |
| SEC-10 | Rotation credentials | ✅ FAIT | JWT_SECRET renforce (hex 64). GATEWAY_ADMIN_KEY deja forte. RabbitMQ: 1 seule instance `rabbitmq-v3` avec creds non-defaut. |
| SEC-1 | Redis vers ILB | ✅ DEJA FAIT | Redis deja sur ILB `10.0.1.220` (namespace `default`). A valider: FW `k8s-fw-*` encore presente? |
| SEC-3 | RabbitMQ vers ILB | ✅ DEJA FAIT | Consolide en 1 instance `rabbitmq-v3` sur ILB `10.0.1.216`. Port `34.78.143.55:15672` ferme. |
| SEC-4 | Qdrant vers ILB | ⬜ A VERIFIER | Qdrant PROD deja ILB. Qdrant DEV (`34.52.142.50`) a verifier. |

---

## Procedure generale

1. **Toujours** prendre un snapshot de l'etat actuel avant modification
2. **Toujours** tester la connectivite inter-services apres chaque changement
3. **Toujours** avoir la commande de rollback prete avant d'executer
4. Executer en fenetre de maintenance (faible trafic)

---

## SEC-1 : Migration Redis vers Internal Load Balancer

### Contexte
Redis est expose publiquement sur `34.14.100.226:6379` via un K8s Service LoadBalancer ou une regle firewall `k8s-fw-a3a81e73236e843ddb15347e6ce6a59d`.

### Etape 1 : Diagnostic

```bash
# 1. Identifier le Service K8s qui expose Redis
kubectl get svc --all-namespaces | grep -i redis

# 2. Verifier le type de Service (LoadBalancer = expose)
kubectl get svc <redis-service-name> -n <namespace> -o yaml

# 3. Identifier la regle firewall associee
gcloud compute firewall-rules describe k8s-fw-a3a81e73236e843ddb15347e6ce6a59d \
  --project=hellopro-rag-project

# 4. Verifier les clients Redis actuels (quels services se connectent)
kubectl get pods --all-namespaces -o yaml | grep -i "redis" | head -20
```

### Etape 2 : Migration vers Internal LB

**Option A : Si Redis est un Service K8s LoadBalancer**

```bash
# Snapshot de la config actuelle
kubectl get svc <redis-service-name> -n <namespace> -o yaml > redis-svc-backup.yaml

# Modifier le Service pour Internal LB
kubectl patch svc <redis-service-name> -n <namespace> -p '{
  "metadata": {
    "annotations": {
      "networking.gke.io/load-balancer-type": "Internal"
    }
  }
}'

# OU supprimer le LB et utiliser ClusterIP (recommande si tout est interne)
kubectl patch svc <redis-service-name> -n <namespace> -p '{"spec": {"type": "ClusterIP"}}'
```

**Option B : Si Redis est expose via une regle firewall manuelle**

```bash
# Restreindre la regle firewall aux ranges internes uniquement
gcloud compute firewall-rules update k8s-fw-a3a81e73236e843ddb15347e6ce6a59d \
  --project=hellopro-rag-project \
  --source-ranges="10.0.0.0/8,172.16.0.0/12,192.168.0.0/16"
```

### Etape 3 : Activer Redis AUTH

```bash
# Si Redis est dans un K8s Deployment
kubectl get deployment -n <namespace> | grep redis

# Creer un Secret K8s pour le mot de passe Redis
kubectl create secret generic redis-auth \
  -n <namespace> \
  --from-literal=redis-password='<MOT_DE_PASSE_FORT_GENERE>'

# Modifier le deployment Redis pour ajouter --requirepass
kubectl edit deployment <redis-deployment> -n <namespace>
# Ajouter dans spec.containers[0].args: ["--requirepass", "$(REDIS_PASSWORD)"]
# Ajouter env: REDIS_PASSWORD from secret redis-auth

# OU si Redis est dans docker-compose sur la VM GPU :
# Modifier docker-compose.yml, ajouter:
#   command: redis-server --requirepass <MOT_DE_PASSE_FORT>
# Puis: docker-compose up -d redis
```

### Etape 4 : Mettre a jour les clients Redis

```bash
# Verifier la variable REDIS_URL dans les services clients
# Ancienne valeur: redis://34.14.100.226:6379
# Nouvelle valeur: redis://:<password>@<internal-ip>:6379

# Lister les services qui utilisent REDIS_URL
grep -r "REDIS_URL\|redis://" docker-compose.yml

# Mettre a jour la valeur dans .env ou docker-compose.yml
# Puis redemarrer les services affectes
```

### Validation

```bash
# Depuis un reseau externe (votre machine locale par ex.)
nmap -p 6379 34.14.100.226
# Resultat attendu: filtered ou closed

# Depuis un pod interne au cluster
kubectl run redis-test --rm -it --image=redis:7-alpine -- \
  redis-cli -h <redis-internal-ip> -a <password> ping
# Resultat attendu: PONG
```

### Rollback

```bash
# Restaurer le Service original
kubectl apply -f redis-svc-backup.yaml

# OU restaurer la regle firewall
gcloud compute firewall-rules update k8s-fw-a3a81e73236e843ddb15347e6ce6a59d \
  --project=hellopro-rag-project \
  --source-ranges="0.0.0.0/0"
```

---

## SEC-2 : Suppression Regle Firewall RDP

### Contexte
La regle `default-allow-rdp` autorise le port 3389 depuis 0.0.0.0/0. Aucun workload Windows n'existe.

### Etape 1 : Diagnostic

```bash
# Verifier la regle
gcloud compute firewall-rules describe default-allow-rdp \
  --project=hellopro-rag-project

# Verifier qu'aucune VM n'utilise le tag associe (si tag cible)
gcloud compute instances list --project=hellopro-rag-project \
  --format="table(name,tags.items)"
```

### Etape 2 : Suppression

```bash
# Sauvegarder la regle avant suppression
gcloud compute firewall-rules describe default-allow-rdp \
  --project=hellopro-rag-project \
  --format=json > firewall-rdp-backup.json

# Supprimer la regle
gcloud compute firewall-rules delete default-allow-rdp \
  --project=hellopro-rag-project \
  --quiet
```

### Validation

```bash
# Verifier suppression
gcloud compute firewall-rules list --project=hellopro-rag-project \
  --filter="name=default-allow-rdp"
# Resultat attendu: Listed 0 items.
```

### Rollback

```bash
# Recreer la regle depuis le backup
gcloud compute firewall-rules create default-allow-rdp \
  --project=hellopro-rag-project \
  --network=default \
  --allow=tcp:3389 \
  --source-ranges=0.0.0.0/0 \
  --description="(Restored) Default allow RDP"
```

---

## SEC-3 : Remediation RabbitMQ Management Expose

### Contexte
RabbitMQ Management UI (15672) et AMQP (5672) sont exposes publiquement via `34.78.143.55`.

### Etape 1 : Diagnostic

```bash
# Identifier les regles firewall concernees
gcloud compute firewall-rules list --project=hellopro-rag-project \
  --filter="allowed[].ports:15672 OR allowed[].ports:5672" \
  --format="table(name,sourceRanges,allowed)"

# Identifier le Service K8s
kubectl get svc --all-namespaces | grep -i rabbit

# Verifier le type de Service
kubectl get svc <rabbitmq-service> -n <namespace> -o yaml
```

### Etape 2 : Restreindre l'acces Management UI

```bash
# Backup des regles concernees
gcloud compute firewall-rules describe allow-public-services \
  --project=hellopro-rag-project \
  --format=json > firewall-public-services-backup.json

# Option 1 : Restreindre aux IPs operateurs pour le management
# Remplacer <IP_CTO>, <IP_DEVSECOPS> par les IPs reelles
gcloud compute firewall-rules update allow-public-services \
  --project=hellopro-rag-project \
  --source-ranges="<IP_CTO>/32,<IP_DEVSECOPS>/32,10.0.0.0/8"

# Option 2 : Si regle separee pour RabbitMQ, la restreindre
gcloud compute firewall-rules update <rabbitmq-firewall-rule> \
  --project=hellopro-rag-project \
  --source-ranges="10.0.0.0/8,172.16.0.0/12,192.168.0.0/16"
```

### Etape 3 : Migration vers Internal LB

```bash
# Backup du Service K8s
kubectl get svc <rabbitmq-service> -n <namespace> -o yaml > rabbitmq-svc-backup.yaml

# Migrer vers Internal LB
kubectl patch svc <rabbitmq-service> -n <namespace> -p '{
  "metadata": {
    "annotations": {
      "networking.gke.io/load-balancer-type": "Internal"
    }
  }
}'

# Mettre a jour les clients RabbitMQ (RABBITMQ_URL dans docker-compose et .env)
# Ancienne: amqp://user:password@34.78.143.55:5672/
# Nouvelle: amqp://user:password@<internal-ip>:5672/
```

### Validation

```bash
# Depuis un reseau externe
nmap -p 15672,5672 34.78.143.55
# Resultat attendu: filtered

# Depuis un pod interne
kubectl run rabbit-test --rm -it --image=curlimages/curl -- \
  curl -u guest:guest http://<rabbitmq-internal-ip>:15672/api/overview
# Resultat attendu: JSON avec info RabbitMQ
```

### Rollback

```bash
kubectl apply -f rabbitmq-svc-backup.yaml

# Restaurer la regle firewall
gcloud compute firewall-rules update allow-public-services \
  --project=hellopro-rag-project \
  --source-ranges="0.0.0.0/0"
```

---

## SEC-4 : Migration Qdrant vers Internal LB

### Contexte
Qdrant expose sur `34.52.142.50` (ports 6333-6335).

### Etape 1 : Diagnostic

```bash
# Identifier le Service K8s Qdrant
kubectl get svc --all-namespaces | grep -i qdrant

# Verifier le type
kubectl get svc <qdrant-service> -n <namespace> -o yaml
```

### Etape 2 : Migration

```bash
# Backup
kubectl get svc <qdrant-service> -n <namespace> -o yaml > qdrant-svc-backup.yaml

# Migrer vers Internal LB
kubectl patch svc <qdrant-service> -n <namespace> -p '{
  "metadata": {
    "annotations": {
      "networking.gke.io/load-balancer-type": "Internal"
    }
  }
}'
```

### Validation

```bash
nmap -p 6333-6335 34.52.142.50
# Resultat attendu: filtered
```

### Rollback

```bash
kubectl apply -f qdrant-svc-backup.yaml
```

---

## SEC-10 : Rotation Credentials par Defaut

### Contexte
Plusieurs credentials par defaut sont en usage, representant un risque d'acces non autorise.

### JWT_SECRET (api-gateway)

```bash
# 1. Generer un nouveau secret
openssl rand -hex 32
# Resultat exemple: a1b2c3d4e5f6...

# 2. Mettre a jour dans l'environnement du service api-gateway
# Si docker-compose sur VM GPU :
#   - Modifier .env ou docker-compose.yml : JWT_SECRET=<nouveau_secret>
#   - Redemarrer : docker-compose restart api-gateway-service

# 3. Si Secret Manager est configure :
# echo -n "<nouveau_secret>" | gcloud secrets versions add jwt-signing-key --data-file=-

# ATTENTION : Invalide tous les tokens JWT existants
# Les utilisateurs devront se reconnecter
```

### GATEWAY_ADMIN_KEY (api-gateway)

```bash
# 1. Generer une nouvelle cle admin
openssl rand -hex 32

# 2. Mettre a jour dans .env / docker-compose.yml
# GATEWAY_ADMIN_KEY=<nouvelle_cle>

# 3. Redemarrer le service
# docker-compose restart api-gateway-service
```

### RabbitMQ Credentials

```bash
# 1. Verifier les credentials actuels
docker exec <rabbitmq-container> rabbitmqctl list_users

# 2. Si guest/guest est actif, le desactiver
docker exec <rabbitmq-container> rabbitmqctl delete_user guest

# 3. Creer un nouvel utilisateur avec mot de passe fort
docker exec <rabbitmq-container> rabbitmqctl add_user <new_user> <strong_password>
docker exec <rabbitmq-container> rabbitmqctl set_permissions -p / <new_user> ".*" ".*" ".*"
docker exec <rabbitmq-container> rabbitmqctl set_user_tags <new_user> administrator

# 4. Mettre a jour RABBITMQ_URL dans tous les services
# Ancienne: amqp://user:password@rabbitmq:5672/
# Nouvelle: amqp://<new_user>:<strong_password>@rabbitmq:5672/

# 5. Redemarrer les services (attention: faire par groupe pour eviter perte de messages)
```

### Checklist Post-Rotation

- [ ] JWT_SECRET mis a jour et service redemarre
- [ ] GATEWAY_ADMIN_KEY mis a jour
- [ ] RabbitMQ guest desactive, nouvel utilisateur cree
- [ ] Tous les services clients mis a jour avec nouvelles credentials
- [ ] Test de connectivite reussi pour chaque service
- [ ] Credentials documentes dans vault securise (PAS dans le repo git)
- [ ] Anciens credentials revoques/invalides

---

## Matrice de Tests Post-Remediation

Apres chaque remediation, verifier la connectivite :

| Source | Destination | Port | Methode de test |
|--------|-------------|------|-----------------|
| VM GPU | Redis (GKE) | 6379 | `redis-cli -h <internal-ip> ping` |
| VM GPU | RabbitMQ (GKE) | 5672 | `curl -u user:pass http://<ip>:15672/api/overview` |
| VM GPU | Milvus (GKE) | 19530 | `curl http://<ip>:19530/v1/vector/collections` |
| VM GPU | Qdrant (GKE) | 6333 | `curl http://<ip>:6333/collections` |
| GKE pods | VM GPU vLLM | 8000 | `curl http://<vm-ip>:8000/health` |
| GKE pods | VM GPU Triton | 8001 | `curl http://<vm-ip>:8001/v2/health/ready` |
| Externe | API Gateway | 8500 | `curl https://<public-url>/health` |

### Script de test global

```bash
#!/bin/bash
# test_connectivity.sh - A executer apres chaque remediation

echo "=== Test Connectivite Post-Remediation ==="

# Variables (a adapter)
REDIS_IP="<redis-internal-ip>"
RABBITMQ_IP="<rabbitmq-internal-ip>"
MILVUS_IP="<milvus-internal-ip>"
QDRANT_IP="<qdrant-internal-ip>"
VM_GPU_IP="<vm-gpu-internal-ip>"

# Tests depuis un pod dans le cluster
kubectl run connectivity-test --rm -it --image=curlimages/curl -- sh -c "
  echo '--- Redis ---'
  nc -zv $REDIS_IP 6379 && echo 'OK' || echo 'FAIL'

  echo '--- RabbitMQ ---'
  curl -sf http://$RABBITMQ_IP:15672/api/overview > /dev/null && echo 'OK' || echo 'FAIL'

  echo '--- Milvus ---'
  curl -sf http://$MILVUS_IP:19530/v1/vector/collections > /dev/null && echo 'OK' || echo 'FAIL'

  echo '--- Qdrant ---'
  curl -sf http://$QDRANT_IP:6333/collections > /dev/null && echo 'OK' || echo 'FAIL'

  echo '--- VM GPU vLLM ---'
  curl -sf http://$VM_GPU_IP:8000/health > /dev/null && echo 'OK' || echo 'FAIL'
"

# Test externe (Redis ne doit PAS repondre)
echo '--- Test Externe (doit echouer) ---'
nc -zv -w 3 34.14.100.226 6379 && echo 'FAIL (encore expose!)' || echo 'OK (filtre)'
nc -zv -w 3 34.78.143.55 15672 && echo 'FAIL (encore expose!)' || echo 'OK (filtre)'
nc -zv -w 3 34.52.142.50 6333 && echo 'FAIL (encore expose!)' || echo 'OK (filtre)'
```

---

## Ordre d'Execution Recommande

1. **SEC-2** : Supprimer RDP (aucun impact, zero risque)
2. **SEC-10** : Rotation credentials (preparation, pas de changement reseau)
3. **SEC-1** : Migration Redis vers ILB (critique, tester connectivite apres)
4. **SEC-3** : RabbitMQ vers ILB (tester consumers apres)
5. **SEC-4** : Qdrant vers ILB (tester services database-qdrant apres)
6. Executer script `test_connectivity.sh` pour validation globale
