 l'amélioration de la performance du moteur de recherche produit, voici la synthèse des tests menés ces derniers jours et l'architecture finale retenue.

I. Synthèse des 4 approches testées

> RAG (sémantique vectoriel) — moteur actuel en partie
Latence : 3 à 5 secondes (embedding CamemBERT + Milvus + rerank)
Qualité : correcte sur intentions floues, mais médiocre sur mots-clés exacts B2B

> Typesense (hybride BM25 + vectoriel)
Latence :  3 à 5 secondes
Qualité API excellente sur queries génériques mais expansion sémantique trop large sur queries spécifiques (ex : pour "ACCOUDOIR GOLF 3", remontait des canapés et salons de jardin par similarité vectorielle "accoudoir = fauteuil")

> OpenSearch (alternative open-source basée sur Lucene, équivalent d'Elasticsearch)
Latence :  3 à 5 secondes
Qualité comparable à Solr en BM25 strict, mais inférieure à Typesense en mode hybride sur notre batterie de tests

> SOLR optimisé (moteur historique retravaillé)
Latence : 2 à 3 secondes (moteur local, BM25 pré-indexé)
Qualité : après optimisations ciblées, note de 8/10 sur les 55 requêtes les plus tapées en prod


Les améliorations apportées à SOLR :
- Pondération des champs revue : nom du produit boosté, catégorie ajoutée, description réduite pour éviter les faux positifs
- Phrase fields : boost supplémentaire quand les mots de la requête apparaissent proches dans le titre (résout les requêtes multi-mots type "machine de découpe")
- Vendeurs certifiés en pole position : boost multiplicatif des produits Client / Pause+Complet
- Boost pertinence : les produits dont le nom contient tous les mots de la requête remontent devant ceux qui ne les ont qu'en description (évite par exemple qu'une "BATTERIE MÉDICALE" remonte sur "armoire médicale" parce qu'"armoire" est mentionné dans sa description)
- Synonymes automatiques générés depuis le catalogue ("minipelle" trouve "Mini-pelle Takeuchi", "Mini-pelle Kubota")
- Découpe automatique des mots composés ("tractopelle" → "tracto pelle"…)


II. Architecture retenue (en 2 couches)

On combine SOLR (vitesse + précision) et Typesense (sémantique + similaires), avec une bascule selon la nature de la requête (si n'arrive pas à trouver 40 produits dans première page, on complète avec recherche hybride chargé par ajax).

Couche 1 : Les 40 premiers produits, par Solr
Couche 2 : Pages 2 à 4, recherche produits par hybride Typesense (sémantique et BM25) en ajax