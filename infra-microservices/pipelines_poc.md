# 🚀 Pipelines du Projet

## 🔹 Pipeline : Demande de Devis
➡️ **Entrée d'une demande de devis**
```
📥 Api-Ingestion (API REST - porte d'entrée)
   ⬇️
📝 Devis-Processor-Service (Nettoyage/autre logique)
   ⬇️
🧩 Embedding-Service (vectorisation)
   ⬇️
🗄️ DI-Database-Qdrant-Service (insertion dans la base vectorielle)
   ⬇️
📢 Webhook-Service (notification / retour de résultat)
```

---

## 🔹 Pipeline : Échange MCF_MCA
➡️ **Traitement d’un échange**
```
📥 Api-Ingestion (API REST - porte d'entrée)
   ⬇️
🔄 Echange-Processor-Service (Nettoyage/autre logique)
   ⬇️
🧩 Embedding-Service (vectorisation)
   ⬇️
🗄️ Echange-Database-Qdrant-Service (insertion dans la base vectorielle)
   ⬇️
📢 Webhook-Service (notification / retour de résultat)
```

---

## 🔹 Pipeline : Site Web
➡️ **Analyse et indexation du site web**
```
📥 Api-Ingestion (API REST - porte d'entrée)
   ⬇️
🌐 Website-Processor-Service (Nettoyage/autre logique)
   ⬇️
🧩 Embedding-Service (transformation en vecteurs)
   ⬇️
🗄️ Website-Database-Qdrant-Service (insertion dans la base vectorielle)
   ⬇️
📢 Webhook-Service (notification / retour de résultat)
```

---

## 🔹 API REST
- api-ingestion  
- Recherche Vectorielle + LLM   
