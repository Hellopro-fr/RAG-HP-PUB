# 💰 Recommandations FinOps - Projet RAG HelloPro GCP

> **Date**: 2026-02-05  
> **Période analysée**: État actuel  
> **Économies potentielles**: ~30-40%

---

## 📊 Estimation des Coûts Actuels

### Compute (VMs)

| Ressource | Type | Zone | Coût estimé/mois |
|-----------|------|------|------------------|
| GKE Nodes (x4) | c2-standard-8 | eu-west1-b | ~$1,100 |
| VM GPU (PROD) | g2-standard-24 | us-east4-c | ~$2,500 |
| VM GPU (TERMINATED) | g2-standard-24 | eu-west1-c | $0 (arrêtée) |
| VM Manager | e2-small | eu-west1-b | ~$15 |
| **Total Compute** | | | **~$3,615/mois** |

### Réseau & Stockage

| Ressource | Coût estimé/mois |
|-----------|------------------|
| Egress réseau | ~$100-200 |
| Load Balancers (22) | ~$200-300 |
| Disques persistants | ~$50-100 |
| **Total Réseau/Stockage** | **~$350-600/mois** |

### Services Managés

| Ressource | Coût estimé/mois |
|-----------|------------------|
| Artifact Registry | ~$10-50 |
| DNS | ~$5 |
| Cloud Logging | Variable |
| **Total Services** | **~$50-100/mois** |

### 📈 Total Estimé: ~$4,000-4,500/mois

---

## 💡 Opportunités d'Optimisation

### 1. VM GPU - Scheduling (Économie: ~$1,000/mois)

**Situation actuelle**: VM GPU 24/7  
**Recommandation**: Arrêt automatique hors heures de travail

```bash
# Scheduler via Cloud Functions ou cron
# Arrêt: 20h → Démarrage: 8h (12h/jour = 50% économie)
```

| Scénario | Heures/jour | Économie |
|----------|-------------|----------|
| 24/7 | 24h | $0 |
| Heures bureau | 12h | ~$1,250 |
| Heures bureau EU | 10h | ~$1,450 |

### 2. Spot/Preemptible Nodes GKE (Économie: ~$500/mois)

**Situation actuelle**: 4 nodes on-demand  
**Recommandation**: Mix on-demand + spot

| Configuration | Coût/mois | Économie |
|---------------|-----------|----------|
| 4x On-demand | $1,100 | $0 |
| 2x On-demand + 2x Spot | ~$700 | ~$400 |
| 1x On-demand + 3x Spot | ~$500 | ~$600 |

> ⚠️ Spot = 60-91% discount mais peut être préempté

### 3. Committed Use Discounts (Économie: ~$800/mois)

**Recommandation**: Engagement 1 ou 3 ans sur ressources stables

| Ressource | Type | CUD 1 an | CUD 3 ans |
|-----------|------|----------|-----------|
| GKE Nodes | c2-standard-8 | -37% | -55% |
| VM GPU | g2-standard-24 | -37% | -55% |

### 4. Right-sizing GKE (Économie potentielle: Variable)

**Analyse requise**:
- Utilisation CPU/RAM actuelle des nodes
- Possibilité de réduire à c2-standard-4

```bash
# Vérifier utilisation
kubectl top nodes
kubectl top pods --all-namespaces
```

### 5. Nettoyage Ressources (Économie: ~$50/mois)

| Ressource | Action |
|-----------|--------|
| VM GPU terminée (eu-west1-c) | Supprimer disques orphelins |
| Subnets non utilisés | Aucun coût, mais clarté |
| IPs statiques non utilisées | Vérifier et supprimer |

---

## 🎯 Plan d'Action FinOps

### Court Terme (1-2 semaines)

| # | Action | Économie | Effort |
|---|--------|----------|--------|
| F1 | Supprimer ressources terminées | ~$20/mois | 🟢 Faible |
| F2 | Implémenter scheduling VM GPU | ~$1,000/mois | 🟡 Moyen |
| F3 | Analyser utilisation GKE | Préparation | 🟢 Faible |

### Moyen Terme (1 mois)

| # | Action | Économie | Effort |
|---|--------|----------|--------|
| F4 | Migrer 2 nodes vers Spot | ~$400/mois | 🟡 Moyen |
| F5 | Right-sizing si applicable | Variable | 🟡 Moyen |
| F6 | Évaluer CUD | ~$800/mois | 🟢 Faible |

### Long Terme (3+ mois)

| # | Action | Économie | Effort |
|---|--------|----------|--------|
| F7 | Négocier CUD 3 ans | ~$1,500/mois | 🟡 Moyen |
| F8 | Optimiser egress réseau | ~$50-100/mois | 🟡 Moyen |
| F9 | Consolider Load Balancers | ~$100/mois | 🔴 Élevé |

---

## 📊 Projection des Économies

| Période | Coût actuel | Après optimisation | Économie |
|---------|-------------|-------------------|----------|
| Mois 1 | $4,200 | $3,200 | $1,000 (24%) |
| Mois 3 | $4,200 | $2,800 | $1,400 (33%) |
| Mois 12 | $4,200 | $2,500 | $1,700 (40%) |

### Économie annuelle potentielle: ~$16,000-20,000

---

## 🔧 Scripts Utiles

### Analyse Utilisation GKE
```bash
# CPU/Memory par node
kubectl top nodes

# Top consumers
kubectl top pods --all-namespaces --sort-by=memory | head -20

# Requests vs Limits
kubectl get pods --all-namespaces -o custom-columns=\
"NAMESPACE:.metadata.namespace,NAME:.metadata.name,CPU_REQ:.spec.containers[*].resources.requests.cpu,MEM_REQ:.spec.containers[*].resources.requests.memory"
```

### Scheduling VM GPU
```bash
# Créer schedule (via Cloud Scheduler + Cloud Functions)
# Ou script cron sur manager-vm

# Stop VM GPU à 20h
gcloud compute instances stop vm-embedding-g2-std-24-use --zone=us-east4-c

# Start VM GPU à 8h
gcloud compute instances start vm-embedding-g2-std-24-use --zone=us-east4-c
```

---

## 📝 Notes

> [!TIP]
> Commencer par le scheduling VM GPU = gain rapide de ~$1,000/mois

> [!WARNING]
> Avant Spot nodes, s'assurer que les workloads tolèrent les interruptions
