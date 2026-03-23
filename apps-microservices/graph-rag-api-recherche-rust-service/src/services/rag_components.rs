/// Prompt templates for RAG components, mirroring Python's rag_components.py.

/// Entity extraction prompt: extracts named entities from a user query.
pub const ENTITY_EXTRACTION_PROMPT: &str = r#"
Tu es un expert en extraction d'entités pour un système de graphe de connaissances.

Extrait les entités suivantes de la requête utilisateur :
- **Produit** : nom ou type de produit mentionné
- **Caractéristique** : propriétés techniques (poids, taille, puissance, etc.)
- **Valeur** : valeurs numériques ou textuelles associées
- **Unité** : unités de mesure
- **Marque** : noms de marques
- **Catégorie** : catégories de produits

Requête : {query}

Réponds en JSON avec la structure suivante :
{{
  "entities": [
    {{"type": "Produit", "value": "..."}},
    {{"type": "Caractéristique", "value": "...", "valeur": "...", "unite": "..."}}
  ]
}}
"#;

/// Routing decision prompt: determines which retrieval strategy to use.
pub const ROUTING_DECISION_PROMPT: &str = r#"
Tu es un routeur intelligent pour un système RAG. Analyse la requête suivante et détermine
la meilleure stratégie de récupération.

Stratégies disponibles :
1. "vectorstore_only" : recherche vectorielle seule (pour les requêtes simples, recherche sémantique)
2. "graph_only" : recherche dans le graphe seul (pour les requêtes relationnelles, liens entre entités)
3. "sequential_refinement" : d'abord le graphe, puis affinement vectoriel (requêtes complexes avec contexte)
4. "parallel_fusion" : les deux en parallèle, puis fusion (requêtes ambiguës ou très larges)

Requête : {query}

Contexte disponible :
- Entités extraites : {entities}

Réponds avec un seul mot : le nom de la stratégie.
"#;

/// Answer generation prompt: generates a final answer from retrieved context.
pub const ANSWER_GENERATION_PROMPT: &str = r#"
Tu es un assistant expert en produits industriels. Génère une réponse complète et structurée
à la requête de l'utilisateur en utilisant le contexte fourni.

Requête : {query}

Contexte :
{context}

Consignes :
- Sois précis et factuel
- Cite les produits et caractéristiques pertinents
- Si l'information est insuffisante, indique-le clairement
- Réponds en français
"#;
