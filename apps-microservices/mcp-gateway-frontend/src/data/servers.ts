import type { PublicToolDetail } from '@/types/public'

export interface ConfigStep {
  title: string
  description: string
  link?: string
  image?: string
}

export interface DocServerConfigGuide {
  authType: string
  steps: ConfigStep[]
}

export interface DocServer {
  slug: string
  name: string
  description: string
  icon?: string
  toolsCount: number
  tools: PublicToolDetail[]
  configGuide?: DocServerConfigGuide
}

export const docServers: DocServer[] = [
  {
    slug: "bdd",
    name: "Base de données",
    description: "Exploration et interrogation en lecture seule de la base de données relationnelle.",
    icon: "/images/servers/bdd.svg",
    toolsCount: 6,
    tools: [
      {
        name: "bdd_describe_table",
        description: "Structure d'une table (colonnes, types, clés, index).",
        input_schema: {"type": "object", "properties": {"table_name": {"type": "string", "description": "Nom de la table"}}, "required": ["table_name"]}
      },
      {
        name: "bdd_get_table_doc",
        description: "Documentation metier d'une table : description, role de chaque colonne, relations et notes. Appeler AVANT d'ecrire une requete pour comprendre le sens des colonnes. Sans parametre = liste toutes les tables documentees.",
        input_schema: {"type": "object", "properties": {"table_name": {"type": "string", "description": "Nom de la table (optionnel, sans = liste toutes)"}}, "required": []}
      },
      {
        name: "bdd_list_tables",
        description: "Liste les tables accessibles avec leur nombre de lignes.",
        input_schema: {"type": "object", "properties": {}, "required": []}
      },
      {
        name: "bdd_query_readonly",
        description: "Exécute un SELECT en lecture seule. Max 2000 lignes. Seuls les SELECT sont autorisés. Bonne pratique : appeler bdd_get_table_doc AVANT pour connaitre la structure et le champ default_order_by. Si la table a un default_order_by, l'utiliser dans ORDER BY. Sinon, trier par cle primaire DESC pour les donnees les plus recentes.",
        input_schema: {"type": "object", "properties": {"sql": {"type": "string", "description": "Requête SELECT à exécuter"}}, "required": ["sql"]}
      },
      {
        name: "bdd_sample_data",
        description: "Retourne 5 lignes d'exemple d'une table.",
        input_schema: {"type": "object", "properties": {"table_name": {"type": "string", "description": "Nom de la table"}}, "required": ["table_name"]}
      },
      {
        name: "bdd_search_columns",
        description: "Recherche des colonnes par nom dans toutes les tables (ex: \"price\", \"email\").",
        input_schema: {"type": "object", "properties": {"column_pattern": {"type": "string", "description": "Motif de recherche"}}, "required": ["column_pattern"]}
      },
    ]
  },
  {
    slug: "google",
    name: "Google Analytics",
    description: "Rapports et configuration Google Analytics 4 : propriétés, dimensions, métriques et rapports temps réel.",
    icon: "/images/servers/google-analytics.svg",
    toolsCount: 7,
    configGuide: {
      authType: "Service Account",
      steps: [
        {
          title: "Créer un projet Google Cloud",
          description: "Accédez à Google Cloud Console et créez un nouveau projet (ou sélectionnez un projet existant).",
          link: "https://console.cloud.google.com/"
        },
        {
          title: "Activer l'API Google Analytics",
          description: "Dans « APIs & Services > Library », recherchez et activez « Google Analytics Data API » et « Google Analytics Admin API »."
        },
        {
          title: "Créer un compte de service",
          description: "Dans « IAM & Admin > Service Accounts », créez un nouveau compte de service. Téléchargez le fichier de clé JSON généré.",
          link: "https://console.cloud.google.com/iam-admin/serviceaccounts"
        },
        {
          title: "Accorder l'accès à la propriété GA4",
          description: "Dans Google Analytics, allez dans « Administration > Gestion des accès à la propriété » et ajoutez l'adresse e-mail du compte de service (ex : mon-service@projet.iam.gserviceaccount.com) avec le rôle « Lecteur »."
        },
        {
          title: "Configurer le serveur MCP",
          description: "Renseignez le contenu du fichier de clé JSON du compte de service dans la configuration du serveur MCP Google Analytics via le panneau d'administration du Gateway."
        },
      ]
    },
    tools: [
      {
        name: "google_get_account_summaries",
        description: "Récupère les informations sur les comptes et propriétés Google Analytics de l'utilisateur.",
        input_schema: {"type": "object", "properties": {}}
      },
      {
        name: "google_get_custom_dimensions_and_metrics",
        description: "Retourne les dimensions et métriques personnalisées de la propriété.\n\nArgs :\n    property_id : L'identifiant de la propriété Google Analytics. Formats acceptés :\n      - Un nombre\n      - Une chaîne composée de 'properties/' suivi d'un nombre",
        input_schema: {"type": "object", "properties": {"property_id": {"anyOf": [{"type": "integer"}, {"type": "string"}]}}}
      },
      {
        name: "google_get_property_details",
        description: "Retourne les détails d'une propriété.\n\nArgs :\n    property_id : L'identifiant de la propriété Google Analytics. Formats acceptés :\n      - Un nombre\n      - Une chaîne composée de 'properties/' suivi d'un nombre",
        input_schema: {"type": "object", "properties": {"property_id": {"anyOf": [{"type": "integer"}, {"type": "string"}]}}}
      },
      {
        name: "google_list_google_ads_links",
        description: "Retourne la liste des liens vers les comptes Google Ads pour une propriété.\n\nArgs :\n    property_id : L'identifiant de la propriété Google Analytics. Formats acceptés :\n      - Un nombre\n      - Une chaîne composée de 'properties/' suivi d'un nombre",
        input_schema: {"type": "object", "properties": {"property_id": {"anyOf": [{"type": "integer"}, {"type": "string"}]}}}
      },
      {
        name: "google_list_property_annotations",
        description: "Retourne les annotations d'une propriété.\n\nLes annotations permettent de laisser des notes sur GA4 pour des dates spécifiques afin de suivre les événements et changements pouvant impacter les métriques.\n\nArgs :\n    property_id : L'identifiant de la propriété Google Analytics. Formats acceptés :\n      - Un nombre\n      - Une chaîne composée de 'properties/' suivi d'un nombre",
        input_schema: {"type": "object", "properties": {"property_id": {"anyOf": [{"type": "integer"}, {"type": "string"}]}}}
      },
      {
        name: "google_run_realtime_report",
        description: "Exécute un rapport temps réel de l'API Google Analytics Data.\n\nConsultez https://developers.google.com/analytics/devguides/reporting/data/v1/rest/v1beta/properties/runRealtimeReport\npour les détails.\n\nArgs :\n    property_id : L'identifiant de la propriété GA4.\n    metrics : Liste de métriques temps réel.\n    dimensions : Liste optionnelle de dimensions.\n    dimension_filter, metric_filter : Filtres optionnels.\n    limit : Nombre max de lignes (défaut : 10000).",
        input_schema: {"type": "object", "properties": {"property_id": {"anyOf": [{"type": "integer"}, {"type": "string"}]}, "dimensions": {"type": "array", "items": {"type": "string"}}, "metrics": {"type": "array", "items": {"type": "string"}}, "dimension_filter": {"type": "object"}, "metric_filter": {"type": "object"}, "order_bys": {"type": "array", "items": {"type": "object"}}, "limit": {"type": "integer"}, "offset": {"type": "integer"}, "return_property_quota": {"type": "boolean"}}}
      },
      {
        name: "google_run_report",
        description: "Exécute un rapport de l'API Google Analytics Data.\n\nConsultez la documentation de référence à\nhttps://developers.google.com/analytics/devguides/reporting/data/v1/rest/v1beta/properties/runReport\npour les détails sur les dimensions et métriques disponibles.\n\nArgs :\n    property_id : L'identifiant de la propriété GA4.\n    date_ranges : Liste de plages de dates (chacune avec start_date et end_date au format YYYY-MM-DD, ou 'today', 'yesterday', 'NdaysAgo').\n    metrics : Liste de métriques à récupérer.\n    dimensions : Liste optionnelle de dimensions.\n    dimension_filter, metric_filter : Filtres optionnels.\n    order_bys : Tri optionnel des résultats.\n    limit : Nombre max de lignes (défaut : 10000).\n    offset : Décalage pour la pagination.",
        input_schema: {"type": "object", "properties": {"property_id": {"anyOf": [{"type": "integer"}, {"type": "string"}]}, "date_ranges": {"type": "array", "items": {"type": "object"}}, "dimensions": {"type": "array", "items": {"type": "string"}}, "metrics": {"type": "array", "items": {"type": "string"}}, "dimension_filter": {"type": "object"}, "metric_filter": {"type": "object"}, "order_bys": {"type": "array", "items": {"type": "object"}}, "limit": {"type": "integer"}, "offset": {"type": "integer"}, "currency_code": {"type": "string"}, "return_property_quota": {"type": "boolean"}}}
      },
    ]
  },
  {
    slug: "googlesearchconsole",
    name: "Google Search Console",
    description: "Données de performance de recherche, inspection d'URL, sitemaps et analyses SEO.",
    icon: "/images/servers/google-search-console.svg",
    toolsCount: 15,
    configGuide: {
      authType: "Service Account",
      steps: [
        {
          title: "Créer un projet Google Cloud",
          description: "Accédez à Google Cloud Console et créez un nouveau projet (ou réutilisez celui de Google Analytics).",
          link: "https://console.cloud.google.com/"
        },
        {
          title: "Activer l'API Search Console",
          description: "Dans « APIs & Services > Library », recherchez et activez « Google Search Console API »."
        },
        {
          title: "Créer un compte de service",
          description: "Dans « IAM & Admin > Service Accounts », créez un nouveau compte de service (ou réutilisez celui de Google Analytics). Téléchargez le fichier de clé JSON.",
          link: "https://console.cloud.google.com/iam-admin/serviceaccounts"
        },
        {
          title: "Ajouter le compte de service à Search Console",
          description: "Dans Google Search Console, allez dans « Paramètres > Utilisateurs et autorisations » et ajoutez l'adresse e-mail du compte de service avec le rôle « Propriétaire » ou « Utilisateur complet ».",
          link: "https://search.google.com/search-console"
        },
        {
          title: "Configurer le serveur MCP",
          description: "Renseignez le contenu du fichier de clé JSON du compte de service dans la configuration du serveur MCP Google Search Console via le panneau d'administration du Gateway."
        },
      ]
    },
    tools: [
      {
        name: "googlesearchconsole_batch_url_inspection",
        description: "Inspection de plusieurs URLs en lot (dans les limites de l'API).\n\nArgs :\n    site_url : L'URL du site dans Search Console.\n    urls : Liste des URLs à inspecter.",
        input_schema: {"properties": {"site_url": {"title": "Site Url", "type": "string"}, "urls": {"title": "Urls", "type": "string"}}, "required": ["site_url", "urls"], "title": "batch_url_inspectionArguments", "type": "object"}
      },
      {
        name: "googlesearchconsole_check_indexing_issues",
        description: "Vérifie les problèmes d'indexation sur plusieurs URLs.\n\nArgs :\n    site_url : L'URL du site dans Search Console.\n    urls : Liste des URLs à vérifier.",
        input_schema: {"properties": {"site_url": {"title": "Site Url", "type": "string"}, "urls": {"title": "Urls", "type": "string"}}, "required": ["site_url", "urls"], "title": "check_indexing_issuesArguments", "type": "object"}
      },
      {
        name: "googlesearchconsole_compare_search_periods",
        description: "Compare les données d'analyse de recherche entre deux périodes.\n\nArgs :\n    site_url : L'URL du site dans Search Console.\n    period1_start, period1_end : Première période.\n    period2_start, period2_end : Deuxième période.\n    dimensions : Dimensions à inclure.",
        input_schema: {"properties": {"site_url": {"title": "Site Url", "type": "string"}, "period1_start": {"title": "Period1 Start", "type": "string"}, "period1_end": {"title": "Period1 End", "type": "string"}, "period2_start": {"title": "Period2 Start", "type": "string"}, "period2_end": {"title": "Period2 End", "type": "string"}, "dimensions": {"default": "query", "title": "Dimensions", "type": "string"}, "limit": {"default": 10, "title": "Limit", "type": "integer"}}, "required": ["site_url", "period1_start", "period1_end", "period2_start", "period2_end"], "title": "compare_search_periodsArguments", "type": "object"}
      },
      {
        name: "googlesearchconsole_get_advanced_search_analytics",
        description: "Récupère les données d'analyse de recherche avancées avec tri, filtrage et pagination.\n\nArgs :\n    site_url : L'URL du site dans Search Console.\n    start_date, end_date : Plage de dates.\n    dimensions : Dimensions à inclure.\n    filters : Filtres à appliquer.\n    row_limit : Nombre max de lignes.\n    start_row : Ligne de départ pour la pagination.",
        input_schema: {"properties": {"site_url": {"title": "Site Url", "type": "string"}, "start_date": {"default": null, "title": "Start Date", "type": "string"}, "end_date": {"default": null, "title": "End Date", "type": "string"}, "dimensions": {"default": "query", "title": "Dimensions", "type": "string"}, "search_type": {"default": "WEB", "title": "Search Type", "type": "string"}, "row_limit": {"default": 1000, "title": "Row Limit", "type": "integer"}, "start_row": {"default": 0, "title": "Start Row", "type": "integer"}, "sort_by": {"default": "clicks", "title": "Sort By", "type": "string"}, "sort_direction": {"default": "descending", "title": "Sort Direction", "type": "string"}, "filter_dimension": {"default": null, "title": "Filter Dimension", "type": "string"}, "filter_operator": {"default": "contains", "title": "Filter Operator", "type": "string"}, "filter_expression": {"default": null, "title": "Filter Expression", "type": "string"}}, "required": ["site_url"], "title": "get_advanced_search_analyticsArguments", "type": "object"}
      },
      {
        name: "googlesearchconsole_get_creator_info",
        description: "Fournit des informations sur Amin Foroutan, le créateur de l'outil MCP-GSC.",
        input_schema: {"properties": {}, "title": "get_creator_infoArguments", "type": "object"}
      },
      {
        name: "googlesearchconsole_get_performance_overview",
        description: "Récupère un aperçu des performances d'une propriété.\n\nArgs :\n    site_url : L'URL du site dans Search Console.\n    days : Nombre de jours à analyser.",
        input_schema: {"properties": {"site_url": {"title": "Site Url", "type": "string"}, "days": {"default": 28, "title": "Days", "type": "integer"}}, "required": ["site_url"], "title": "get_performance_overviewArguments", "type": "object"}
      },
      {
        name: "googlesearchconsole_get_search_analytics",
        description: "Récupère les données d'analyse de recherche pour une propriété spécifique.\n\nArgs :\n    site_url : L'URL du site dans Search Console.\n    start_date : Date de début (format YYYY-MM-DD).\n    end_date : Date de fin (format YYYY-MM-DD).\n    dimensions : Dimensions pour le regroupement.\n    row_limit : Nombre max de lignes.",
        input_schema: {"properties": {"site_url": {"title": "Site Url", "type": "string"}, "days": {"default": 28, "title": "Days", "type": "integer"}, "dimensions": {"default": "query", "title": "Dimensions", "type": "string"}}, "required": ["site_url"], "title": "get_search_analyticsArguments", "type": "object"}
      },
      {
        name: "googlesearchconsole_get_search_by_page_query",
        description: "Récupère les données d'analyse de recherche pour une page spécifique, ventilées par requête.\n\nArgs :\n    site_url : L'URL du site dans Search Console.\n    page_url : L'URL de la page à analyser.\n    start_date, end_date : Plage de dates.",
        input_schema: {"properties": {"site_url": {"title": "Site Url", "type": "string"}, "page_url": {"title": "Page Url", "type": "string"}, "days": {"default": 28, "title": "Days", "type": "integer"}}, "required": ["site_url", "page_url"], "title": "get_search_by_page_queryArguments", "type": "object"}
      },
      {
        name: "googlesearchconsole_get_site_details",
        description: "Récupère les informations détaillées d'une propriété Search Console.\n\nArgs :\n    site_url : L'URL du site.",
        input_schema: {"properties": {"site_url": {"title": "Site Url", "type": "string"}}, "required": ["site_url"], "title": "get_site_detailsArguments", "type": "object"}
      },
      {
        name: "googlesearchconsole_get_sitemap_details",
        description: "Récupère les informations détaillées d'un sitemap spécifique.\n\nArgs :\n    site_url : L'URL du site dans Search Console.\n    sitemap_url : L'URL du sitemap.",
        input_schema: {"properties": {"site_url": {"title": "Site Url", "type": "string"}, "sitemap_url": {"title": "Sitemap Url", "type": "string"}}, "required": ["site_url", "sitemap_url"], "title": "get_sitemap_detailsArguments", "type": "object"}
      },
      {
        name: "googlesearchconsole_get_sitemaps",
        description: "Liste tous les sitemaps d'une propriété Search Console.\n\nArgs :\n    site_url : L'URL du site.",
        input_schema: {"properties": {"site_url": {"title": "Site Url", "type": "string"}}, "required": ["site_url"], "title": "get_sitemapsArguments", "type": "object"}
      },
      {
        name: "googlesearchconsole_inspect_url_enhanced",
        description: "Inspection d'URL améliorée pour vérifier l'état d'indexation et les résultats enrichis dans Google.\n\nArgs :\n    site_url : L'URL du site dans Search Console.\n    inspection_url : L'URL à inspecter.",
        input_schema: {"properties": {"site_url": {"title": "Site Url", "type": "string"}, "page_url": {"title": "Page Url", "type": "string"}}, "required": ["site_url", "page_url"], "title": "inspect_url_enhancedArguments", "type": "object"}
      },
      {
        name: "googlesearchconsole_list_properties",
        description: "Récupère et retourne les propriétés Search Console de l'utilisateur.",
        input_schema: {"properties": {}, "title": "list_propertiesArguments", "type": "object"}
      },
      {
        name: "googlesearchconsole_list_sitemaps_enhanced",
        description: "Liste tous les sitemaps d'une propriété Search Console avec des informations détaillées.\n\nArgs :\n    site_url : L'URL du site.",
        input_schema: {"properties": {"site_url": {"title": "Site Url", "type": "string"}, "sitemap_index": {"default": null, "title": "Sitemap Index", "type": "string"}}, "required": ["site_url"], "title": "list_sitemaps_enhancedArguments", "type": "object"}
      },
      {
        name: "googlesearchconsole_manage_sitemaps",
        description: "Outil tout-en-un pour gérer les sitemaps (lister, détails, soumettre, supprimer).\n\nArgs :\n    site_url : L'URL du site.\n    action : L'action à effectuer (list, get, submit, delete).\n    sitemap_url : L'URL du sitemap (requis pour get, submit, delete).",
        input_schema: {"properties": {"site_url": {"title": "Site Url", "type": "string"}, "action": {"title": "Action", "type": "string"}, "sitemap_url": {"default": null, "title": "Sitemap Url", "type": "string"}, "sitemap_index": {"default": null, "title": "Sitemap Index", "type": "string"}}, "required": ["site_url", "action"], "title": "manage_sitemapsArguments", "type": "object"}
      },
    ]
  },
  {
    slug: "leexi",
    name: "Leexi",
    description: "Accès aux appels et réunions Leexi : recherche, transcriptions et résumés IA.",
    icon: "/images/servers/leexi.svg",
    toolsCount: 3,
    configGuide: {
      authType: "Clé API",
      steps: [
        {
          title: "Accéder aux paramètres Leexi",
          description: "Connectez-vous à votre compte Leexi et accédez à la section « Paramètres > Intégrations » ou « API ».",
          link: "https://app.leexi.ai/"
        },
        {
          title: "Générer une clé API",
          description: "Créez une nouvelle clé API depuis le tableau de bord Leexi. Copiez la clé générée — elle ne sera plus affichée par la suite."
        },
        {
          title: "Configurer le serveur MCP",
          description: "Renseignez la clé API dans la configuration du serveur MCP Leexi via le panneau d'administration du Gateway (champ LEEXI_API_KEY)."
        },
      ]
    },
    tools: [
      {
        name: "leexi_get_call_summary",
        description: "Récupère le résumé généré par IA d'un appel ou d'une réunion par UUID. Inclut les prompts/compléments IA, les chapitres et les sujets clés.",
        input_schema: {"type": "object", "properties": {"call_uuid": {"type": "string", "description": "L'identifiant unique (UUID) de l'appel ou de la réunion"}}, "required": ["call_uuid"]}
      },
      {
        name: "leexi_get_call_transcript",
        description: "Récupère la transcription complète d'un appel ou d'une réunion par UUID. Retourne la transcription horodatée au niveau des paragraphes et des mots avec attribution des interlocuteurs.",
        input_schema: {"type": "object", "properties": {"call_uuid": {"type": "string", "description": "L'identifiant unique (UUID) de l'appel ou de la réunion"}}, "required": ["call_uuid"]}
      },
      {
        name: "leexi_search_calls",
        description: "Rechercher et lister les appels/réunions depuis Leexi. Prend en charge le filtrage par plage de dates, le tri, le filtrage par propriétaire et la pagination.",
        input_schema: {"type": "object", "properties": {"from": {"type": "string", "description": "Date de début du filtre (ISO 8601, ex : 2026-04-01T00:00:00.000Z)"}, "to": {"type": "string", "description": "Date de fin du filtre (ISO 8601, ex : 2026-04-03T23:59:59.000Z)"}, "order": {"type": "string", "description": "Ordre de tri des résultats", "enum": ["created_at desc", "created_at asc", "performed_at desc", "performed_at asc", "updated_at desc", "updated_at asc"], "default": "created_at desc"}, "owner_uuid": {"type": "string", "description": "Filtrer par UUID du propriétaire de l'appel"}, "with_simple_transcript": {"type": "boolean", "description": "Inclure le texte de la transcription dans les résultats (défaut : false)", "default": false}, "page": {"type": "integer", "description": "Numéro de page pour la pagination (défaut : 1)", "default": 1}, "items": {"type": "integer", "description": "Nombre de résultats par page (1-100, défaut : 10)", "default": 10}}}
      },
    ]
  },
  {
    slug: "neo4j",
    name: "Neo4j Graph Database",
    description: "Lecture du graphe Neo4j : schéma et requêtes Cypher en lecture seule.",
    icon: "/images/servers/neo4j.svg",
    toolsCount: 2,
    tools: [
      {
        name: "neo4j_get_neo4j_schema",
        description: "Retourne les nœuds, leurs propriétés (avec types et indicateurs d'index) et les relations\nen utilisant l'inspection de schéma APOC.\n\nUtilisez cet outil en premier pour comprendre la structure du graphe avant d'écrire des requêtes Cypher.",
        input_schema: {"properties": {"sample_size": {"default": 1000, "description": "Taille de l'échantillon pour inférer le schéma du graphe. Un échantillon plus grand est plus lent mais plus précis. Un plus petit est plus rapide mais peut manquer des informations.", "type": "integer"}}, "type": "object"}
      },
      {
        name: "neo4j_read_neo4j_cypher",
        description: "Exécute une requête Cypher en lecture seule sur la base de données Neo4j.",
        input_schema: {"properties": {"query": {"description": "La requête Cypher à exécuter.", "type": "string"}, "params": {"additionalProperties": true, "default": {}, "description": "Les paramètres à passer à la requête Cypher.", "type": "object"}}, "required": ["query"], "type": "object"}
      },
    ]
  },
  {
    slug: "rag",
    name: "RAG Pipeline",
    description: "Pipeline RAG HelloPro : embeddings, recherche vectorielle, recherche par filtres, reranking et chat LLM.",
    icon: "/images/servers/rag.svg",
    toolsCount: 6,
    tools: [
      {
        name: "rag_classic_search",
        description: "Rechercher dans une collection Milvus par filtres uniquement (sans recherche vectorielle ni re-ranking). IMPORTANT : avant d'utiliser cet outil, appelez d'abord get_collection_schema pour découvrir les champs disponibles et filtrables, puis construisez vos filtres en utilisant uniquement les champs marqués comme filterable. Cet outil est idéal pour les requêtes structurées (par ID, catégorie, fournisseur, date, etc.) où la similarité sémantique n'est pas nécessaire. Collections disponibles : produits_3 (produits), siteweb_2 (sites web), devis (devis), echanges (conversations), prix (tarifs).",
        input_schema: {"type": "object", "properties": {"collection": {"type": "string", "enum": ["produits_3", "siteweb_2", "devis", "echanges", "prix"], "description": "Nom de la collection Milvus à interroger"}, "filters": {"type": "object", "description": "Filtres clé-valeur à appliquer (ex. {\"fournisseur\": \"ACME\", \"categorie\": \"Pompes\"}). Appelez get_collection_schema au préalable pour connaître les champs filtrables."}, "top_k": {"type": "integer", "description": "Nombre maximum de résultats à retourner", "default": 10}, "output_fields": {"type": "array", "items": {"type": "string"}, "description": "Champs spécifiques à inclure dans les résultats (obligatoire : appelez get_collection_schema au préalable pour connaître les champs disponibles, puis ne demandez que ceux dont vous avez besoin). Ne pas renseigner ce champ retourne tous les champs, ce qui est déconseillé."}}, "required": ["collection", "filters"]}
      },
      {
        name: "rag_embed_text",
        description: "Convertir du texte en vecteurs d'embedding de 1024 dimensions à l'aide du modèle CamemBERT-large. Utile pour calculer la similarité entre des textes ou pour des flux de recherche personnalisés. Supporte le traitement par lots de plusieurs textes.",
        input_schema: {"type": "object", "properties": {"texts": {"type": "array", "items": {"type": "string"}, "description": "Liste de textes à convertir en embeddings (traitement par lots supporté)"}}, "required": ["texts"]}
      },
      {
        name: "rag_get_collection_schema",
        description: "Récupérer le schéma (noms et types des champs) d'une collection Milvus. Utilisez cet outil pour découvrir les champs disponibles pour le filtrage et les output_fields pouvant être demandés lors d'une recherche. Collections disponibles : produits_3 (produits), siteweb_2 (sites web), devis (devis), echanges (conversations), prix (tarifs).",
        input_schema: {"type": "object", "properties": {"collection": {"type": "string", "description": "Nom de la collection Milvus (ex. produits_3, siteweb_2, devis, echanges, prix)"}}, "required": ["collection"]}
      },
      {
        name: "rag_llm_chat",
        description: "Envoyer un prompt au service LLM interne (modèles hébergés via vLLM). À utiliser uniquement lorsque vous avez besoin d'une réponse d'un modèle spécifique hébergé dans l'infrastructure HelloPro, pas pour du chat généraliste.",
        input_schema: {"type": "object", "properties": {"message": {"type": "string", "description": "Le message prompt à envoyer au LLM"}, "temperature": {"type": "number", "description": "Température d'échantillonnage (0.0 = déterministe, 1.0 = créatif)", "default": 0.0}, "max_tokens": {"type": "integer", "description": "Nombre maximum de tokens dans la réponse", "default": 4096}}, "required": ["message"]}
      },
      {
        name: "rag_rerank",
        description: "Re-classer une liste de documents textuels par pertinence par rapport à une requête à l'aide d'un modèle cross-encoder (BAAI/bge-reranker-v2-m3). Retourne les documents triés par pertinence avec leurs scores. Utile lorsque vous avez des résultats de recherche et souhaitez les réordonner par pertinence par rapport à une requête affinée.",
        input_schema: {"type": "object", "properties": {"query": {"type": "string", "description": "La requête par rapport à laquelle classer les documents"}, "documents": {"type": "array", "items": {"type": "string"}, "description": "Liste de documents textuels à re-classer"}}, "required": ["query", "documents"]}
      },
      {
        name: "rag_search",
        description: "Rechercher dans la base de connaissances HelloPro à travers les catalogues produits, sites web, devis, échanges et bases de données de prix. IMPORTANT : avant d'utiliser cet outil, appelez d'abord get_collection_schema pour découvrir les champs disponibles de chaque collection, puis spécifiez uniquement les champs nécessaires via output_fields au lieu de récupérer tous les champs. Supporte la recherche sémantique vectorielle, la recherche par mots-clés/filtres, et la recherche hybride (vecteur + BM25). Les résultats sont optionnellement re-classés par pertinence à l'aide d'un modèle cross-encoder. Retourne des correspondances structurées regroupées par collection source avec métadonnées et scores de pertinence.",
        input_schema: {"type": "object", "properties": {"query": {"type": "string", "description": "La requête de recherche en langage naturel (français ou anglais)"}, "sources": {"type": "array", "description": "Collections à rechercher. Chaque entrée spécifie un nom de source et des filtres optionnels. Sources disponibles : produits_3 (produits), siteweb_2 (sites web), devis (devis), echanges (conversations), prix (tarifs)", "items": {"type": "object", "properties": {"source": {"type": "string", "enum": ["produits_3", "siteweb_2", "devis", "echanges", "prix"]}, "filters": {"type": "object", "description": "Filtres clé-valeur appliqués à cette source (ex. {\"fournisseur\": \"ACME\"})"}}, "required": ["source"]}, "default": [{"source": "produits_3"}]}, "top_k": {"type": "integer", "description": "Nombre maximum de résultats à retourner par source", "default": 10}, "filters": {"type": "object", "description": "Filtres globaux appliqués à toutes les sources (ex. {\"fournisseur\": \"ACME\", \"avec_prix\": true})"}, "output_fields": {"type": "array", "items": {"type": "string"}, "description": "Champs spécifiques à inclure dans les résultats (obligatoire : appelez get_collection_schema au préalable pour connaître les champs disponibles, puis ne demandez que ceux dont vous avez besoin). Ne pas renseigner ce champ retourne tous les champs, ce qui est déconseillé."}, "search_type": {"type": "string", "enum": ["semantic", "keyword", "hybrid"], "description": "Mode de recherche : 'semantic' (embedding + similarité vectorielle), 'keyword' (filtres uniquement, sans embeddings), 'hybrid' (vecteur dense + BM25 plein texte)", "default": "semantic"}, "use_reranker": {"type": "boolean", "description": "Indique s'il faut re-classer les résultats à l'aide d'un modèle cross-encoder (BAAI/bge-reranker-v2-m3) pour un meilleur classement par pertinence", "default": true}}, "required": ["query"]}
      },
    ]
  },
  {
    slug: "ringover",
    name: "Ringover",
    description: "Accès aux appels téléphoniques Ringover : historique, détails et recherche.",
    icon: "/images/servers/ringover.svg",
    toolsCount: 3,
    configGuide: {
      authType: "Clé API",
      steps: [
        {
          title: "Accéder au Dashboard Ringover",
          description: "Connectez-vous à votre compte Ringover et accédez au Dashboard d'administration.",
          link: "https://dashboard.ringover.com/"
        },
        {
          title: "Générer un token API",
          description: "Allez dans « Développeurs > API » et générez un nouveau token d'accès. Copiez le token — il ne sera plus affiché par la suite."
        },
        {
          title: "Configurer le serveur MCP",
          description: "Renseignez le token API dans la configuration du serveur MCP Ringover via le panneau d'administration du Gateway (champ RINGOVER_API_TOKEN)."
        },
      ]
    },
    tools: [
      {
        name: "ringover_get_call_details",
        description: "Récupère les informations détaillées d'un appel spécifique.",
        input_schema: {"type": "object", "properties": {"call_id": {"type": "string", "description": "L'identifiant unique de l'appel"}}, "required": ["call_id"]}
      },
      {
        name: "ringover_list_calls_by_date",
        description: "Liste les appels dans une plage de dates. Les dates doivent être au format ISO 8601 (ex : 2026-04-01T00:00:00.000Z) ou AAAA-MM-JJ.",
        input_schema: {"type": "object", "properties": {"start_date": {"type": "string", "description": "Début de la plage de dates (ISO 8601 ou AAAA-MM-JJ)"}, "end_date": {"type": "string", "description": "Fin de la plage de dates (ISO 8601 ou AAAA-MM-JJ)"}, "limit": {"type": "integer", "description": "Nombre maximum d'appels à retourner (défaut : 50)", "default": 50}}, "required": ["start_date", "end_date"]}
      },
      {
        name: "ringover_search_calls",
        description: "Recherche et filtre les appels par type, numéro de téléphone ou utilisateur. Tous les paramètres sont optionnels. Utilisez call_type pour filtrer par ANSWERED (entrants/sortants répondus), MISSED (entrants manqués), OUT (sortants), VOICEMAIL.",
        input_schema: {"type": "object", "properties": {"call_type": {"type": "string", "description": "Filtrer par type d'appel : ANSWERED (entrant/sortant répondu), MISSED (entrant manqué), OUT (sortant), VOICEMAIL", "enum": ["ANSWERED", "MISSED", "OUT", "VOICEMAIL"]}, "phone_number": {"type": "string", "description": "Filtrer par numéro de téléphone (appelant ou appelé)"}, "user_id": {"type": "string", "description": "Filtrer par identifiant utilisateur Ringover"}, "limit": {"type": "integer", "description": "Nombre maximum de résultats (défaut : 20)", "default": 20}}}
      },
    ]
  },
  {
    slug: "semrush",
    name: "SEMrush",
    description: "Données SEO et SEM : mots-clés, backlinks, concurrents, annonces et analyses de domaines.",
    icon: "/images/servers/semrush.svg",
    toolsCount: 16,
    configGuide: {
      authType: "Clé API",
      steps: [
        {
          title: "Accéder aux paramètres SEMrush",
          description: "Connectez-vous à votre compte SEMrush et accédez à « Subscription Info » ou « API » dans les paramètres du compte.",
          link: "https://www.semrush.com/accounts/subscription-info/"
        },
        {
          title: "Copier la clé API",
          description: "Votre clé API est affichée dans la section « API key ». Un plan SEMrush Business ou supérieur est requis pour certaines fonctionnalités (backlinks, domaines référents)."
        },
        {
          title: "Configurer le serveur MCP",
          description: "Renseignez la clé API dans la configuration du serveur MCP SEMrush via le panneau d'administration du Gateway (champ SEMRUSH_API_KEY)."
        },
      ]
    },
    tools: [
      {
        name: "semrush_backlinks",
        description: "Backlinks d'un domaine : liste des liens entrants. Nécessite un plan SEMrush Business.",
        input_schema: {"type": "object", "properties": {"target": {"type": "string", "description": "Domaine ou URL à analyser (ex : hellopro.fr)"}, "target_type": {"type": "string", "description": "Type de cible : root_domain, domain ou url. Défaut : root_domain"}, "display_limit": {"type": "integer", "description": "Nombre de backlinks (défaut : 10)"}}, "required": ["target"]}
      },
      {
        name: "semrush_backlinks_domains",
        description: "Domaines référents (sources de backlinks) d'un domaine. Nécessite un plan SEMrush Business.",
        input_schema: {"type": "object", "properties": {"target": {"type": "string", "description": "Domaine à analyser (ex : hellopro.fr)"}, "target_type": {"type": "string", "description": "Type de cible : root_domain, domain ou url. Défaut : root_domain"}, "display_limit": {"type": "integer", "description": "Nombre de domaines référents (défaut : 10)"}}, "required": ["target"]}
      },
      {
        name: "semrush_batch_keyword_overview",
        description: "Métriques pour plusieurs mots-clés en une seule requête (max 100 mots-clés).",
        input_schema: {"type": "object", "properties": {"keywords": {"type": "array", "items": {"type": "string"}, "description": "Liste de mots-clés à analyser (max 100)"}, "database": {"type": "string", "description": "Base de données pays (défaut : us)"}}, "required": ["keywords"]}
      },
      {
        name: "semrush_broad_match_keywords",
        description: "Variantes de mots-clés en correspondance large contenant l'expression.",
        input_schema: {"type": "object", "properties": {"keyword": {"type": "string", "description": "Mot-clé pour trouver des correspondances larges"}, "database": {"type": "string", "description": "Base de données pays (défaut : us)"}, "display_limit": {"type": "integer", "description": "Nombre de résultats (défaut : 10)"}}, "required": ["keyword"]}
      },
      {
        name: "semrush_competitors",
        description: "Concurrents en recherche organique d'un domaine.",
        input_schema: {"type": "object", "properties": {"domain": {"type": "string", "description": "Domaine dont chercher les concurrents"}, "database": {"type": "string", "description": "Base de données pays (défaut : us)"}, "display_limit": {"type": "integer", "description": "Nombre de concurrents (défaut : 10)"}}, "required": ["domain"]}
      },
      {
        name: "semrush_domain_organic_keywords",
        description: "Mots-clés organiques pour lesquels un domaine est positionné dans les résultats de recherche.",
        input_schema: {"type": "object", "properties": {"domain": {"type": "string", "description": "Domaine à analyser"}, "database": {"type": "string", "description": "Base de données pays (défaut : us)"}, "display_limit": {"type": "integer", "description": "Nombre max de mots-clés à retourner (défaut : 10)"}}, "required": ["domain"]}
      },
      {
        name: "semrush_domain_overview",
        description: "Aperçu des performances SEO organiques d'un domaine : rang, trafic, mots-clés, backlinks.",
        input_schema: {"type": "object", "properties": {"domain": {"type": "string", "description": "Domaine à analyser (ex : hellopro.fr)"}, "database": {"type": "string", "description": "Code de base de données pays (ex : fr, us, uk). Défaut : us"}}, "required": ["domain"]}
      },
      {
        name: "semrush_domain_paid_keywords",
        description: "Mots-clés payants sur lesquels un domaine enchérit dans Google Ads.",
        input_schema: {"type": "object", "properties": {"domain": {"type": "string", "description": "Domaine à analyser"}, "database": {"type": "string", "description": "Base de données pays (défaut : us)"}, "display_limit": {"type": "integer", "description": "Nombre max de mots-clés (défaut : 10)"}}, "required": ["domain"]}
      },
      {
        name: "semrush_keyword_ads_history",
        description: "Historique des données Google Ads pour un mot-clé (qui a fait de la publicité, quand, à quelle position).",
        input_schema: {"type": "object", "properties": {"keyword": {"type": "string", "description": "Mot-clé à analyser"}, "database": {"type": "string", "description": "Base de données pays (défaut : us)"}}, "required": ["keyword"]}
      },
      {
        name: "semrush_keyword_difficulty",
        description: "Score de difficulté du mot-clé (0-100) : indique la difficulté à se positionner organiquement sur ce mot-clé.",
        input_schema: {"type": "object", "properties": {"keyword": {"type": "string", "description": "Mot-clé dont vérifier la difficulté"}, "database": {"type": "string", "description": "Base de données pays (défaut : us)"}}, "required": ["keyword"]}
      },
      {
        name: "semrush_keyword_organic_results",
        description: "Résultats SERP organiques (pages les mieux classées) pour un mot-clé.",
        input_schema: {"type": "object", "properties": {"keyword": {"type": "string", "description": "Mot-clé à analyser"}, "database": {"type": "string", "description": "Base de données pays (défaut : us)"}, "display_limit": {"type": "integer", "description": "Nombre de résultats (défaut : 10)"}}, "required": ["keyword"]}
      },
      {
        name: "semrush_keyword_overview",
        description: "Métriques d'un mot-clé dans toutes les bases de données (aperçu global : volume, CPC, concurrence).",
        input_schema: {"type": "object", "properties": {"keyword": {"type": "string", "description": "Mot-clé à analyser"}, "database": {"type": "string", "description": "Base de données pays (défaut : us)"}}, "required": ["keyword"]}
      },
      {
        name: "semrush_keyword_overview_single_db",
        description: "Métriques détaillées d'un mot-clé pour un pays/une base de données spécifique.",
        input_schema: {"type": "object", "properties": {"keyword": {"type": "string", "description": "Mot-clé à analyser"}, "database": {"type": "string", "description": "Base de données pays (défaut : us)"}}, "required": ["keyword"]}
      },
      {
        name: "semrush_keyword_paid_results",
        description: "Résultats publicitaires payants pour un mot-clé (annonceurs et leurs annonces).",
        input_schema: {"type": "object", "properties": {"keyword": {"type": "string", "description": "Mot-clé à analyser"}, "database": {"type": "string", "description": "Base de données pays (défaut : us)"}, "display_limit": {"type": "integer", "description": "Nombre de résultats (défaut : 10)"}}, "required": ["keyword"]}
      },
      {
        name: "semrush_phrase_questions",
        description: "Mots-clés sous forme de questions contenant l'expression (qui, quoi, comment, pourquoi...).",
        input_schema: {"type": "object", "properties": {"keyword": {"type": "string", "description": "Mot-clé/expression pour trouver des questions"}, "database": {"type": "string", "description": "Base de données pays (défaut : us)"}, "display_limit": {"type": "integer", "description": "Nombre de mots-clés questions (défaut : 10)"}}, "required": ["keyword"]}
      },
      {
        name: "semrush_related_keywords",
        description: "Mots-clés sémantiquement liés à un mot-clé de base.",
        input_schema: {"type": "object", "properties": {"keyword": {"type": "string", "description": "Mot-clé de base"}, "database": {"type": "string", "description": "Base de données pays (défaut : us)"}, "display_limit": {"type": "integer", "description": "Nombre de mots-clés liés (défaut : 10)"}}, "required": ["keyword"]}
      },
    ]
  },
  {
    slug: "zohocrm",
    name: "Zoho CRM",
    description: "Outils d'accès au CRM Zoho : modules, enregistrements, notes, requêtes COQL et listes liées.",
    icon: "/images/servers/zoho.svg",
    toolsCount: 15,
    configGuide: {
      authType: "OAuth2 (Zoho MCP)",
      steps: [
        {
          title: "Accéder au portail Zoho MCP",
          description: "Rendez-vous sur mcp.zoho.eu et connectez-vous avec votre compte Zoho.",
          link: "https://mcp.zoho.eu/"
        },
        {
          title: "Créer une connexion MCP",
          description: "Depuis le portail, créez une nouvelle connexion MCP pour Zoho CRM. Sélectionnez les modules et permissions souhaités (lecture des enregistrements, COQL, etc.)."
        },
        {
          title: "Récupérer les identifiants de connexion",
          description: "Copiez le Client ID et le Client Secret générés par le portail Zoho MCP."
        },
        {
          title: "Configurer le serveur MCP",
          description: "Renseignez le Client ID et le Client Secret dans la configuration du serveur MCP Zoho CRM via le panneau d'administration du Gateway."
        },
      ]
    },
    tools: [
      {
        name: "ZohoCRM_executeCOQLQuery",
        description: "Exécute une requête COQL de type SELECT pour récupérer des données d'enregistrements.",
        input_schema: {"type": "object", "properties": {"body": {"description": "Corps de la requête pour récupérer des données via COQL", "properties": {"include_meta": {"description": "Liste des métadonnées à inclure. Actuellement, seul 'fields' est supporté pour les métadonnées de colonnes.", "items": {"description": "Type de métadonnée à inclure", "enum": ["fields"], "type": "string"}, "type": "array"}, "select_query": {"description": "Requête COQL SELECT pour récupérer les données", "maxLength": 2147483647, "type": "string"}}, "required": ["select_query"], "type": "object"}}, "required": ["body"]}
      },
      {
        name: "ZohoCRM_getFields",
        description: "Récupère les métadonnées de tous les champs d'un module. Exemples et schémas dérivés des fichiers d'exemples et de schémas fournis.",
        input_schema: {"type": "object", "properties": {"query_params": {"properties": {"include": {"description": "Inclure des informations supplémentaires sur les permissions de mise à jour du champ.", "enum": ["allowed_permissions_to_update", "skip_field_permissionz"], "maxLength": 50, "type": "string"}, "module": {"description": "Le nom API du module auquel le champ appartient.", "maxLength": 30, "type": "string"}, "type": {"description": "Le type de champs à récupérer. Exemple : 'used', 'unused', etc.", "enum": ["all", "unused", "used"], "maxLength": 10, "type": "string"}}, "required": ["module", "include"], "type": "object"}}, "required": ["query_params"]}
      },
      {
        name: "ZohoCRM_getModules",
        description: "Récupère les métadonnées des modules CRM : configuration, capacités et informations structurelles. Prend en charge le filtrage par nom de fonctionnalité, statut de visibilité et métadonnées optionnelles supplémentaires.",
        input_schema: {"type": "object", "properties": {"query_params": {"properties": {"feature_name": {"description": "Filtrer les modules par nom de fonctionnalité. Sensible à la casse, format snake_case.", "enum": ["Kiosk_Test_Run", "sales_motivator_games_users", "functions", "linkingmodule_custom_field_long_integer", "smart_prompt_zia_llm", "voc_parent", "linkingmodule_custom_field_dataparam", "mb_delete_limit_popup", "unsubscribe", "query_sources", "field_updates", "crl_queries_click", "web_case", "google_instant_booking", "emailsai_summary_translation", "ASKZIA_MODULE_CREATION", "static_subform_max_rows", "triggers", "public_field", "custom_field_datetime", "extensions", "mass_email", "nextgenui_new_panel_enabled", "connected_workflows_limit", "CANVAS_META_CACHE_REVERTER", "send_mail_attachments_total_count", "date_queries", "production_tracking", "nbx_early_access", "picklist colour coding V2", "custom_field_dataparam", "teammodule_custom_field", "address_field_enabled", "data_storage_count", "privacy_modules", "email_relay", "manage_signals", "wizard_cross_screen_fields_in_criteria", "page_layout", "sample_subfeature_1", "zoho_reports", "hipaa_compliance", "custom_dashboards", "imap", "Kiosk_Screens", "abm", "massconvert_dealcreation_newflow", "best_mode_to_contact_special_access", "action_field_update_product_configurator", "send_mail_inventory_module", "bounce_email_block", "reports", "personal_health_fields", "Lead_Status_Mapping", "CANVAS_META_CACHE", "analytics", "create_record", "anomaly_notifications", "organize_tabs", "wf_di_notification", "pathfinder_processing_count", "Kiosk", "detailview_customization", "orchestration_execution_limit", "export", "picklist colour coding", "detailview_canvasrules", "duplicate_check_preference", "bigin_domain_mapping", "web_tabs", "Kiosk_GetRecords_Fetch_limit", "custom_field_decision_box", "emailsai_test_account", "notes_short_content", "lookup_filter_new_mapping", "email_notifications", "exchange", "portal_readonlymodule", "custom_field_imageupload", "bcc_dropbox", "gsuite", "writing_assistant", "adwords", "roles", "voc", "consent_email", "disable_nio_flow", "custom_button_api_name_page_lyte", "linkingmodule_custom_field_radio", "firstname_limit_increase_revert", "autofollowup_rules", "microsoft_office", "support_access", "records_limit_custom_view", "zoho_mobile_edition", "outlook", "DATA_BRIDGE", "association_per_global_field", "subform_custom_field_check_box", "WF_BH_FLOW_CHANGE", "rfm_segmentation_contribution_module", "bulk_write", "file_storage_per_user", "event_rsvp_update", "slack", "custom_related_list", "cscript_dotsdk_spec_flow", "QuickML_Integration", "zia_config", "linkingmodule_custom_field_date", "mass_convert", "price_rule_volume", "smart_prompt_new_bot", "zia_agent_in_cb", "kiosk_versions_wise", "record_level_sharing_groups", "linkingmodule_custom_field_rich_text", "printview_customization", "LZ_FAAS_TEST", "linkingmodule_custom_field_imageupload", "related_list_customization", "portals_signup_form", "gdpr_lyte_revamp", "zia_agent", "email_storage_ui", "email_templates_attachments_total_size", "global_picklist_colourCode", "zoho_projects", "Stage_Probability_Mapping", "email_parser", "web_apps", "email_intent_workflow", "FX_CREDITS_STATIC_ISSUE_FIX", "Stage_Used_Option_Count", "user_licenses", "data_storage", "REPORT_FORMULA_DYNAMIC_GROUP_LIMIT", "Kiosk_Components", "zoho_campaigns", "canvas_reusable_component", "comparator", "custom_field_date", "custom_field_text_area", "web_vendor", "abm_segment_export", "Kiosk_GetRecord_Selection_Limit", "organization_emails", "cscript_mxn_field", "email_storage_trigger_resync", "wizards", "email_storage_phase2", "functions_minimum_calls", "voc_inventory", "external_share_record", "email_authentication", "microsoft_teams", "smart_prompt_googleai_llm", "pages", "wizard_cscript_transition_begin", "best_time_to_contact", "zia_vision", "zoho_fsm", "zia_summary", "zoho_contracts", "zia_summary_multilanguage_support", "custom_field_url", "sales_motivator_dashboards", "detailview_canvasfiles", "custom_field_phone", "linkingmodule_custom_field_lookup", "schedule_mail", "mobilecanvas_kiosk_support", "zia_sales_recommendation", "business_card", "shift_hours", "instant_sync_cvid", "CHATBOT_MULTILINGUAL", "firstname_limit_increase", "used_option_count", "smart_prompt_in_cb", "calendar_schedule_user_event", "rfm_record_processing_count", "linkingmodule_custom_field_url", "path_finder_version_wise", "unused_option_count", "record_tags_count", "emailConfigFeatures", "zoho_expense", "bounce_email", "next_best_action", "field_level_security", "portal_personalitymodule", "domain_mappings", "custom_function_upgrade", "gmail_rest_api", "custom_field_check_box", "talk_with_us_zoho_voice_call", "email_workflow", "intergration", "sandbox", "AUTOMATIC_ANOMALY_ENCH_2", "notify_owner", "mobiledetailview_customization", "territory_management", "custom_field_formula", "copy_customization", "form_rules_actions", "functions_limits", "scoring_rules", "sales_signals_mobile_notification_support", "custom_link", "Stage_Total_Option_Count", "inventory_management", "accessibility", "team_module_requester_settings", "dxeditor_m1", "email_templates", "auto_response_rules", "campaign_hierarchy_depth", "sandbox_email_support", "journey_limit_increase", "Bundles__s", "excluded_profiles", "subform_allowed_file_limit", "abm_product", "MS_GRAPH_API", "sales_motivator_dashboards_comp", "zia_score_special_access", "feeds_autofollowuprules_support", "zoho_circuits_pricing", "linkingmodule_custom_field_fileupload", "email_duplication", "linkingmodule_custom_field_percentage", "webform_multidomain", "bigin_dashboards_new_signup", "abm_widget", "zia_call_transcription_cops", "email_credibility", "scheduled_mass_email", "emailparser", "FormviewCustomization", "custommodule", "zcircuits_free_execution_per_month", "orchestration_actions", "homepage_report_components", "BUSINESS_HOURS_SANDBOX", "business_hours", "pdf_sendmail_to_contacts", "auto_responders", "custom_field_small_text_area", "zia_record_summary_special_access", "orchestration_versions_wise", "mail_merge", "connected_workflows", "multicurrency", "zoho_invoice", "file_storage_base", "data_sharing_rules_criteria", "linkingmodule_custom_field_decimal", "waterfall", "connected_records", "web_multimodule_fields", "ListviewCustomization", "activity_badge_upgrade", "abm_contact", "record_level_sharing_indirect_groups", "homepage_components", "abm_plus", "form_rules", "services", "mail_apps", "validation_rule_custom_function", "linkingmodule_custom_field_phone", "payments_integration", "cscript_reports", "store_widget", "custom_field_long_integer", "workflow_rules_summary", "chart", "multipipelines", "cscript_commands", "REPORT_FORMULA_DYNAMIC_SELECT_LIMIT", "text_case_intelligence", "zoho_sign", "voc_sales", "zoho_mail", "record_clone", "multi_page_layout", "input_options_gs", "custom_ai_solutions", "portal_users_store_widget", "holidays", "component_suggestion_early_access", "cscript_dotsdk_new_flow", "email_emotion_analysis", "linkedIn_sales_navigator", "chat_support", "cscript_support_in_portals", "custom_field_integer", "subform_custom_field_large_text_area", "custom_link_new_tab", "recommendation_early_access_new_dc", "custom_field_email", "tiktok_leadchain", "MS_21VIANET", "webform_abtesting", "abm_churn", "telephony", "large_global_set", "mass_delete", "portal_users", "portal_authorizationmodule", "form_rules_branch_criteria_per_condition", "import", "subform_custom_field_small_text_area", "module_builder_new_ui", "zoho_forms", "subform_multiple_fileupload", "ZOHOCPQ", "abm_voc", "team_module_requester_settings_disable", "global_picklists", "live_chat", "zoho_support", "calendar_schedule_team_event", "zoho_circuits", "encrypt_field", "activity_calendar", "disable_ecw_recipient", "zia_call_analytics_automation", "switch_edition", "mb_lyte_qc_enabled", "homeview_customization", "Kiosk_GetRecords_Fetch", "blueprint_states", "calendar_schedule_team_call", "funnel", "subform_encrypt_field", "subform_custom_field_text_area", "CANVAS_BP_MANDATORY_CSCRIPT", "zia_summary_special_access", "ews_mailapps_integ", "datahub", "hamburger_menu_recommended_section", "abm_account", "twitter", "smart_prompt_anthropic_llm_special_access", "zcircuits_free_execution_per_user", "sales_motivator_games_rules", "Kiosk_Screen_Max_Buttons", "quadrant", "custom_reports", "sentiment_analysis", "webform analytics cleanup duration", "system_address_field_enabled", "custom_field_radio", "criteria_entities_product_configurator", "web_custommodule", "CLIENTPORTAL_FOOTER_HIDING", "zia_supported_deployment", "zoho_bookings", "price_rule_direct", "blueprint_transitions", "linkingmodule_custom_field_radiobutton", "custom_field_currency", "calendar_schedule_user", "enable_record_state", "zia_scoring_rule", "form_rules_primary_condition", "module_deleted_core_flow", "call_transcription_early_access", "emailsai_selfmarketing", "disable_composer_default_spellcheck", "zoho_showtime", "schedule_mass_operation", "emails_ai", "Zoho_Docs", "custom_field_cfpool_userlookup", "gsearch_auto_complete", "blueprint_transition_during_fields", "google_calendar", "cscript_preload", "nextgenui_setuphome_enabled", "guided_selling", "emailFeatures", "api_trigger_limit", "smart_prompt_in_cb_special_access", "visitor_tracking", "mb_new_header", "REPORT_FORMULA_DYNAMIC_CRITERIA_LIMIT", "abm_deal", "rename_tabs", "cscript_subform_row_lock_function", "notes_badge_listview", "smart_prompt_cohere_llm", "validation_rules", "zia_conversation_summary_special_access", "subform_module_max_rows_crud", "linkingmodule_custom_field_decision_box", "zone", "bigin_dashboards_enabled", "global_picklist_per_module", "ear_for_email", "external_field", "cscript_multiuserlookup_field", "rules_limit_per_module", "marketplace", "linkingmodule_custom_field_text_area", "portal_users_new", "Translation_Workbench", "dynamic_lookup_filter", "subform", "linkingmodule_custom_field_text", "homepage_quick_link_components", "validation_rule_primary_condition", "forecasts", "mobilecanvas_navigator", "automation_new_massmail_sources_enabled", "Kiosk_Draft_Execution", "Lyte_Stage_Probability_Mapping", "cpq_dashboard_v2_2_support", "hide_unauthorized_create_link", "best_time_analytics_segmentation_access", "copy_customization_interdc", "custom_function_schedulers", "custom_field_decimal", "change_owner", "appsspace_enabled", "portal_parentmodule", "business_messages", "macros_suggest", "abm_data_enrichment", "portal_user_list_page_landing", "sales_motivator_tvchannels", "similarity_early_access", "email_templates_attachments_total_count", "crm_widgets", "notes_rich_text_support_disable", "zia_copilot", "workflow_rules_executeon_safieldupdate", "team_module_enabled", "mailmerge_email", "cscript", "Kiosk_Execution_Per_User", "trend_analysis", "ZRC", "module_limit_per_process", "zia_anomaly", "lux", "detailview_queries_association", "event_meeting_config", "canvas_clickto_ajaxedit", "chart_view", "office365", "sample_feature_1", "mailchimp", "abm_mood_score", "tags", "event_participants_reminder", "workflow_suggestion", "c3", "abm_rel_flow_demo", "web_forms", "blueprint_common_transitions", "di_cases_access", "zia_reminder", "nbx_goal", "private_fields", "duplicate_image_detection_special_access", "sales_motivator_games_teams", "CANVAS_FILES_UDSDOWNLOAD", "linkingmodule_custom_field_currency", "mass_update_by_cvid", "dynamic_groups_product_configurator", "web_lead", "participants_limit", "best_time_analytics_early_access", "zia_summary_multilanguage_support_special_access", "smart_prompt_deepseek_llm_special_access", "linkingmodule_custom_field_pick_list", "custom_field", "mapview_and_autosuggest", "remote_sales_office", "data_storage_limits_more_than_200_user", "modules_prediction", "stage", "text_product_intelligence", "zia_owner_recommendation", "emailcatchAllFeatures", "sales_motivator_games", "action_entities_product_configurator", "unique_field", "teamdrive", "deduplication_tool", "target_meter", "inventory_templates", "google_docs", "record_level_sharing_indirect_roles", "record_locking_configurations", "query_workbench", "Map_Dependency_Fields", "IS_MAKING_NOTES_RT_NULL_ENABLED", "CHATBOT_QUERY_SUGGESTION", "ms_calendar", "custom_ai_studio", "sandbox_partial_deployment", "custom_field_percentage", "best_time_analytics_special_access", "data_migration", "feeds_followed_records_support", "custom_field_large_text_area", "data_enrichment", "people_enrichment", "phonebridge", "smart_prompt_anthropic_llm", "canvas_grid_layout", "customer_usage_data", "cadences", "custom_functions", "bm_line_integration", "sales_motivator", "cohort", "DT_Filter", "portals_authorization_criteria_count", "custom_field_mxn", "compliance_settings", "apiname_page_corruption_view_enabled", "custom_field_picklist", "best_mode_to_contact", "leadchain", "subform_max_rows_crud_v2", "Kiosk_GetRecord_Selection_Limit_Fetch", "nextgenui_enabled", "form_rules_branch_condition", "api_name_page_lyte", "webform_analytics_revamp", "zia_score", "voc_dashboard_limit", "linking_module", "web_contact", "question_pages_gs", "ciscoteams", "custom_field_lookup", "price_rule", "calendar_schedule_user_call", "SHIFT_IMPORT", "presentation_special_access", "schedule_call", "linkedin_leadchain", "leads_prediction", "CHATBOT_V2_SPECIAL_ACCESS", "keyboard_shortcuts", "subForm_configured_fields", "free_data_backup", "intelligent_character_recognition", "ASKZIA_WORKFLOW_CREATION", "ListviewFromImageToCanvas", "recommendation", "custom_list_views", "custom_field_aggregate_fields", "smart_prompt", "zia_conversation_summary", "field_encryption", "CANVAS_SERVICE", "canvas_detailview_rl_scope", "approval_processes", "notes_rich_text_support", "pitch", "tasks", "team_spaces", "anomaly_notifications_new", "export_xlsx", "query_associations", "portals", "pathfinder_instance_creation_limit", "crm_variables", "zoho_cliq", "di_cases_access_ee", "calendar_schedule_team_per_service", "zoho_backstage", "people_enrichment_isc", "voc_computation_keyword_limit", "subform_permissions", "workflow_report", "user_associations_module_users", "mass_transfer", "CHATBOT_NEW_UI_ENABLED", "customize_setup", "workflow_rules_executeon_sectionupdate", "zia_copilot_language_support", "zia_in_email", "google_contacts", "picklist_history_tracking", "workflow_rules_executeon_fieldupdate", "Kiosk_GetRecords", "calendar_booking", "abm_recommendation", "unique_chk_for_contacts", "portal_user_group_new_ui", "webform_fields_limit", "record_level_sharing_users", "webhooks", "abm_suggested_segments", "subform_max_rows_crud", "subform_v2", "ListviewCanvasRulesLimit", "workflow_rules", "cscript_notes_events", "teamspace_enabled", "subform_module_max_rows_crud_v2", "google_chat", "send_mail", "people_enrichment_extension_migration", "zia_call_analytics", "homepage_kiosk_components", "custom_field_multi_select", "dup_chk_preference", "workflow", "writing_assistant_special_access", "voc_for_loweredition", "notes_edit_delete_by_owner", "abm_recommendation_kakfa_disable", "abm_tour", "booking_pages", "duplicate_image_detection", "workflow_rules_executeon_datetime", "report_export_daily", "call_transcription", "AI_CREDITS", "prediction", "calendar_schedule_team", "cscript_uploadfields_events", "zia_voice", "abm_segment_journey_limit", "zoho_assist", "cscript_subform_feild_set_visible_function", "record_level_sharing_roles", "relay_smtp_debug", "nbx_goal_ui", "customview_sandbox_support", "macro", "teammodule", "multiselect_filter_options", "assignment_rules", "social", "mailcollabview", "presentation_dc", "multicurrency_nf", "total_validation_rules", "Kiosk_Association_Limit_Per_Page", "locking_rules", "pathfinder_limit_increase", "nbx_live_update", "data_storage_per_user", "email_in", "custom_field_radio_button", "schedule_reports", "smart_prompt_siliconflow_llm", "full_data_sandbox", "subject_line_suggestion", "workflow_time_based_actions", "mass_update", "zoho_webinar", "workflow_rules_executeon_delete_plugin", "salesinbox", "text_call_intelligence", "zoho_docs", "emailsai_selfmarketing_phase2", "voc_anonymous", "excluded_fields", "voc_primary", "abm_engagement_score", "linkingmodule_custom_field", "smart_prompt_special_access", "executable_file_upload_restrict", "pop_up_reminders", "trends", "custom_pages", "send_mail_attachments_total_size", "custom_field_auto_number", "text_note_intelligence", "zoho_pagesense", "sales_motivator_rules", "sales_motivator_tvchannels_comp", "product_configurator", "salesinbox_mobile", "split_view_enabled", "total_data_sharing_rules", "google_instant_booking_profile", "customization", "mobile_apps", "lead_conversion_layoutrule", "smart_prompt_zia_llm_special_access", "add_meeting", "record_image", "email_insights", "path_finder", "email", "email_authorisation", "zoho_survey", "churn_prediction", "assign_owner", "report_aggregates_limit", "custom_field_multi_select_multi_module_lookup", "component_suggestion", "dashboards_cache_reduced", "prm_feature_enabled", "Kiosk_Data_Hub", "route_iq", "price_rule_range", "client_portal_saml_configuration", "presentation", "rfm_draft", "linkingmodule_custom_field_small_text_area", "linkingmodule_custom_field_check_box", "canvas_flex_layout", "sales_motivator_targets", "crl_queries", "feedback_mechanism", "subform_permissions_disable", "CSCRIPT_ORG_ZAPPS_RETRY", "data_storage_per_user_more_than_200_user", "admin_center", "sales_motivator_teams_users", "tab_groups", "voc_component_limit", "data_sharing_rules", "subform_custom_field_pick_list", "Lookup_Filter", "records_limit", "custom_field_userlookup", "reports_scheduled", "recommendation_for_workflow", "case_escalation_rules", "FORMULA_DYNAMIC_CRITERIA_LIMIT", "workflow_rules_executeon_delete", "zoho_sheet", "zoho_flow_pricing", "sky_eye", "webform_analytics_url_revamp", "linkingmodule_custom_field_large_text_area", "linkingmodule_custom_field_integer", "webform_suggestions", "disable_sandbox_emailconsumer", "smart_prompt_cohere_llm_special_access", "similarity", "schedules", "field_prevent_duplicate", "zoho_creator", "zia_score_automation", "email_storage", "assignment_thresholds", "facebook_leadchain", "inc_used_option_count", "subform_custom_field", "listview_queries_association", "cv_anomaly", "user_associations_admin_users", "reporting_hierarchy", "smart_filters_limit", "integration_email", "subform_bulk_addition_max_rows", "custom_field_text", "smart_prompt_new_bot_v2_special_access", "zia_record_summary", "sales_signals", "rfm_segmentation", "form_rules_picklist_values_overall", "data_sharing", "zoho_flow", "blueprints", "user_type", "zia", "validation_rule_branch_condition", "record_state_options_limit", "booking_event_participant_limit", "smart_prompt_googleai_llm_special_access", "module_summary", "search_layout", "Competitors_Alert", "marketing_attribution", "abm_limit_enhancement", "nextgenui_user_settings_preference", "catalyst_solutions", "EXTERNAL_MODULE_CONFIG", "gmail", "best_time_analytics", "custom_field_fileupload", "record_level_sharing", "multiple_kanban_view", "audit_logs", "Closure_Restrictions", "linkingmodule_custom_field_multi_select", "functions_call_per_user", "zia_scoring_rule_special_access", "zia_pitch_special_access", "mailbox_mails_population", "additional_pipelines", "text_meeting_intelligence", "chatbot", "facebook", "user_associations", "custom_field_multiuserlookup", "smart_prompt_new_bot_v2", "CSCRIPT_PAGES_MIGRATION", "bigin_dashboards_enabled_trigger", "caldav", "smart_prompt_deepseek_llm", "zia_field_creation", "zoho_circuits_execution", "custom_field_rich_text", "custom_button", "linkingmodule_custom_field_datetime", "reminders", "review_process", "zcircuits_max_execution_per_month", "RELATED_LIST_FIELDS", "sales_motivator_teams", "smart_prompt_siliconflow_llm_special_access", "revert_connected_records", "dashboards_enabled", "CHATBOT_DETAIL_VIEW", "report_export_records_limit", "webform_analytics", "Bundle_Product_Relations__s", "email_sending_restriction", "kpi", "events_notification_mail", "profiles", "record_level_sharing_indirect_users", "recommendation_early_access", "text_email_intelligence", "colourcode_option_count", "fx_mics", "custom_field_cfpool_lookup", "sandbox_data_population_modules", "CanvasRevisions", "email_sharing", "kanban_view", "static_resource", "connected_records_for_org_modules", "CANVAS_LV_CSCRIPT", "linkedin", "presentation_early_access", "custom_field_address_field", "file_cabinet", "m360_newmail_queue", "custom_button_in_zia_widgets", "zoho_campaigns_create", "lead_chain", "form_rules_picklist_values_per_condition", "groups", "email_attachments", "microsoft_outlook", "zia_call_audio_transcription", "gamification", "prediction_analytics", "zoho_subscription", "email_analytics", "ZIA_DASHBOARD_COMPANION", "cscript_subform_events", "linkingmodule_custom_field_email", "restricted_custom_buttons", "zoho_lens"], "type": "string"}, "include": {"description": "Liste séparée par des virgules des champs supplémentaires à inclure dans la réponse.", "maxLength": 3000, "type": "string"}, "status": {"description": "Filtrer les modules par statut de visibilité. Accepte des valeurs séparées par des virgules. Sensible à la casse.", "maxLength": 56, "type": "string"}}, "required": [], "type": "object"}}, "required": []}
      },
      {
        name: "ZohoCRM_getNoteById",
        description: "Récupère les détails d'une note spécifique par son identifiant.",
        input_schema: {"type": "object", "properties": {"path_variables": {"properties": {"id": {"description": "Identifiant unique de la note", "format": "int64", "type": "string"}}, "required": ["id"], "type": "object"}, "query_params": {"properties": {"fields": {"description": "Liste séparée par des virgules des noms API de champs à inclure", "maxLength": 1024, "type": "string"}}, "required": [], "type": "object"}}, "required": ["path_variables"]}
      },
      {
        name: "ZohoCRM_getNotes",
        description: "Récupère une liste paginée des notes associées à un enregistrement parent d'un module CRM.",
        input_schema: {"type": "object", "properties": {"path_variables": {"properties": {"parentRecordId": {"description": "L'identifiant unique de l'enregistrement parent. Doit être un ID numérique valide.", "format": "int64", "type": "string"}, "parentRecordModule": {"description": "Le nom API du module de l'enregistrement parent (ex : Contacts, Leads, Deals, Accounts)", "maxLength": 50, "type": "string"}}, "required": ["parentRecordModule", "parentRecordId"], "type": "object"}, "query_params": {"properties": {"fields": {"description": "Liste séparée par des virgules des noms de champs à inclure. Les noms doivent suivre les conventions API.", "maxLength": 1000, "type": "string"}, "page": {"default": 1, "description": "Numéro de page (à partir de 1)", "format": "int32", "maximum": 10000, "minimum": 1, "type": "integer"}, "perPage": {"default": 200, "description": "Nombre d'enregistrements par page", "format": "int32", "maximum": 200, "minimum": 1, "type": "integer"}, "sort_by": {"description": "Nom du champ pour le tri des notes", "enum": ["id", "Created_Time", "Modified_Time"], "maxLength": 50, "type": "string"}, "sort_order": {"description": "Ordre de tri des résultats", "enum": ["asc", "desc"], "maxLength": 10, "type": "string"}}, "required": [], "type": "object"}}, "required": ["path_variables"]}
      },
      {
        name: "ZohoCRM_getNotesById",
        description: "Récupère les détails d'un enregistrement de note associé à un enregistrement parent d'un module CRM.",
        input_schema: {"type": "object", "properties": {"path_variables": {"properties": {"noteId": {"description": "L'identifiant unique de la note. Doit être un ID numérique valide.", "format": "int64", "type": "string"}, "parentRecordId": {"description": "L'identifiant unique de l'enregistrement parent. Doit être un ID numérique valide.", "format": "int64", "type": "string"}, "parentRecordModule": {"description": "Le nom API du module de l'enregistrement parent (ex : Contacts, Leads, Deals, Accounts)", "maxLength": 50, "type": "string"}}, "required": ["parentRecordModule", "parentRecordId", "noteId"], "type": "object"}}, "required": ["path_variables"]}
      },
      {
        name: "ZohoCRM_getNotesModule",
        description: "Récupère la liste des notes.",
        input_schema: {"type": "object", "properties": {"query_params": {"properties": {"fields": {"description": "Liste séparée par des virgules des noms API de champs à inclure", "maxLength": 1024, "type": "string"}, "ids": {"description": "Liste séparée par des virgules des ID de notes à récupérer", "maxLength": 1024, "type": "string"}, "page": {"description": "Numéro de page pour la pagination", "format": "int32", "type": "integer"}, "page_token": {"description": "Jeton de page pour récupérer plus de 2000 enregistrements", "maxLength": 2000, "type": "string"}, "per_page": {"description": "Nombre d'enregistrements par page", "format": "int32", "type": "integer"}, "sort_by": {"description": "Nom du champ pour le tri", "enum": ["Modified_Time", "Created_Time", "id"], "type": "string"}, "sort_order": {"description": "Ordre de tri (croissant ou décroissant)", "enum": ["asc", "desc"], "type": "string"}}, "required": [], "type": "object"}}, "required": []}
      },
      {
        name: "ZohoCRM_getRecord",
        description: "Récupère les détails d'un enregistrement spécifique par son identifiant unique.",
        input_schema: {"type": "object", "properties": {"path_variables": {"properties": {"module": {"description": "Le nom API du module sur lequel effectuer l'opération. Les modules système incluent Leads, Accounts, Contacts, Deals, Campaigns, Tasks, Cases, Meetings, Calls, Solutions, Products, Vendors, Price_Books, Quotes, Sales_Orders, Purchase_Orders, Invoices, Appointments, Appointments_Rescheduled_History et Services. Les modules personnalisés sont également supportés. Utilisez le nom API du module (ex : Leads, Price_Books).", "maxLength": 100, "type": "string"}, "recordID": {"description": "Cet identifiant est utilisé pour identifier de manière unique un enregistrement", "format": "int64", "type": "string"}}, "required": ["recordID", "module"], "type": "object"}}, "required": ["path_variables"]}
      },
      {
        name: "ZohoCRM_getRecordCount",
        description: "Récupère le nombre total d'enregistrements d'un module spécifié.\nLe décompte peut être filtré par `cvid` (ID de vue personnalisée) ou par d'autres critères.",
        input_schema: {"type": "object", "properties": {"path_variables": {"properties": {"moduleApiName": {"description": "Le nom API du module (ex : Leads, Accounts).", "maxLength": 5000, "type": "string"}}, "required": ["moduleApiName"], "type": "object"}, "query_params": {"properties": {"approved": {"description": "true pour compter uniquement les leads convertis ; false pour les non-convertis.", "enum": ["true", "false", "both"], "type": "string"}, "converted": {"description": "true pour compter uniquement les leads convertis ; false pour les non-convertis.", "enum": ["true", "false", "both"], "type": "string"}, "criteria": {"description": "Chaîne de critères de recherche avec nom API du champ, opérateur et valeur", "maxLength": 3000, "type": "string"}, "cvid": {"description": "L'ID de vue personnalisée pour filtrer les enregistrements.", "maxLength": 3000, "type": "string"}, "email": {"description": "L'adresse e-mail pour filtrer. Les caractères spéciaux doivent être encodés en URL.", "maxLength": 3000, "type": "string"}, "page": {"default": 1, "description": "Le numéro de page pour la pagination.", "format": "int32", "minimum": 1, "type": "integer"}, "per_page": {"default": 200, "description": "Nombre d'enregistrements par page.", "format": "int32", "maximum": 200, "minimum": 1, "type": "integer"}, "phone": {"description": "Le numéro de téléphone pour filtrer.", "maxLength": 3000, "type": "string"}, "type": {"description": "Spécifie le type d'utilisateur pour le filtrage.", "enum": ["AllUsers", "ActiveUsers", "DeactiveUsers", "ConfirmedUsers", "ConfirmedReportingUsers", "NotConfirmedUsers", "DeletedUsers", "ActiveConfirmedUsers", "AdminUsers", "ActiveConfirmedAdmins", "CurrentUser"], "type": "string"}, "word": {"description": "Le mot pour filtrer les enregistrements.", "maxLength": 3000, "type": "string"}}, "required": [], "type": "object"}}, "required": ["path_variables"]}
      },
      {
        name: "ZohoCRM_getRecords",
        description: "Récupère la liste des enregistrements disponibles d'un module.",
        input_schema: {"type": "object", "properties": {"path_variables": {"properties": {"module": {"description": "Le nom API du module sur lequel effectuer l'opération. Les modules système incluent Leads, Accounts, Contacts, Deals, Campaigns, Tasks, Cases, Meetings, Calls, Solutions, Products, Vendors, Price_Books, Quotes, Sales_Orders, Purchase_Orders, Invoices, Appointments, Appointments_Rescheduled_History et Services. Les modules personnalisés sont également supportés. Utilisez le nom API du module (ex : Leads, Price_Books).", "maxLength": 100, "type": "string"}}, "required": ["module"], "type": "object"}, "query_params": {"properties": {"converted": {"description": "Récupérer la liste des enregistrements convertis", "enum": ["false", "true", "both"], "type": "string"}, "cvid": {"description": "Spécifier l'ID de vue personnalisée pour obtenir la liste des enregistrements", "format": "int64", "type": "string"}, "fields": {"description": "Spécifier les noms API des champs à récupérer.", "maxLength": 1024, "type": "string"}, "ids": {"description": "Récupérer des enregistrements spécifiques par leur identifiant unique.", "maxLength": 1024, "type": "string"}, "include_child": {"description": "Inclure les enregistrements des territoires enfants", "type": "boolean"}, "page": {"description": "Récupérer la liste des enregistrements des pages respectives", "format": "int32", "type": "integer"}, "page_token": {"description": "Pour récupérer plus de 2000 enregistrements, inclure le paramètre page_token", "maxLength": 100, "type": "string"}, "per_page": {"description": "Nombre d'enregistrements par page", "format": "int32", "type": "integer"}, "sort_by": {"description": "Trier les enregistrements par id, Created_Time ou Modified_Time. Défaut : 'id'", "enum": ["id", "Created_Time", "Modified_Time"], "type": "string"}, "sort_order": {"description": "Trier les enregistrements en ordre croissant ou décroissant", "enum": ["desc", "asc"], "type": "string"}, "territory_id": {"description": "Spécifier l'ID du territoire pour filtrer les enregistrements", "format": "int64", "type": "string"}}, "required": [], "type": "object"}}, "required": ["path_variables"]}
      },
      {
        name: "ZohoCRM_getRelatedLists",
        description: "Récupère la configuration des listes liées pour un module et un layout spécifiques.",
        input_schema: {"type": "object", "properties": {"query_params": {"properties": {"layout_id": {"description": "Identifiant unique du layout pour lequel récupérer les listes liées", "maxLength": 20, "minLength": 1, "type": "string"}, "module": {"description": "Nom API du module CRM (ex : Leads, Contacts, Accounts)", "enum": ["Leads", "Contacts", "Accounts", "Deals", "Tasks", "Events", "Calls", "Products", "Quotes", "Sales_Orders", "Purchase_Orders", "Invoices", "Campaigns", "Vendors", "Price_Books", "Cases", "Solutions"], "type": "string"}, "status": {"description": "Filtrer les listes liées par statut de visibilité", "enum": ["visible", "scheduled_for_deletion", "user_hidden"], "type": "string"}}, "required": ["module"], "type": "object"}}, "required": ["query_params"]}
      },
      {
        name: "ZohoCRM_getRelatedRecord",
        description: "Récupère les détails d'un enregistrement lié spécifique à un enregistrement parent. Retourne les données avec la pagination.",
        input_schema: {"type": "object", "properties": {"path_variables": {"properties": {"parentRecord": {"description": "L'identifiant unique de l'enregistrement parent. Doit être un ID numérique valide.", "maxLength": 20, "type": "string"}, "parentRecordModule": {"description": "Le nom du module de l'enregistrement parent (ex : Contacts, Leads, Deals, Accounts)", "maxLength": 100, "type": "string"}, "record": {"description": "L'identifiant unique de l'enregistrement lié. Doit être un ID numérique valide.", "maxLength": 20, "type": "string"}, "relatedList": {"description": "Le nom de la liste liée (module) contenant les enregistrements", "maxLength": 100, "type": "string"}}, "required": ["parentRecordModule", "parentRecord", "relatedList", "record"], "type": "object"}, "query_params": {"properties": {"fields": {"description": "Liste séparée par des virgules des noms de champs à inclure. Les noms doivent suivre les conventions API.", "maxLength": 1000, "type": "string"}}, "required": ["fields"], "type": "object"}}, "required": ["query_params", "path_variables"]}
      },
      {
        name: "ZohoCRM_getRelatedRecords",
        description: "Récupère une liste paginée d'enregistrements d'une liste liée spécifique d'un enregistrement parent. Prend en charge le filtrage par statut de conversion, ID de vue personnalisée et sélection de champs.",
        input_schema: {"type": "object", "properties": {"headers": {"properties": {"If-Modified-Since": {"description": "Retourner uniquement les enregistrements modifiés après cette date (format RFC 2822)", "format": "date-time", "type": "string"}}, "required": [], "type": "object"}, "path_variables": {"properties": {"parentRecord": {"description": "L'identifiant unique de l'enregistrement parent. Doit être un ID numérique valide.", "maxLength": 20, "type": "string"}, "parentRecordModule": {"description": "Le nom du module de l'enregistrement parent (ex : Contacts, Leads, Deals, Accounts)", "maxLength": 100, "type": "string"}, "relatedList": {"description": "Le nom de la liste liée (module) contenant les enregistrements", "maxLength": 100, "type": "string"}}, "required": ["parentRecordModule", "parentRecord", "relatedList"], "type": "object"}, "query_params": {"properties": {"converted": {"default": "false", "description": "Filtrer les enregistrements convertis.", "enum": ["true", "false", "both"], "type": "string"}, "fields": {"description": "Liste séparée par des virgules des noms de champs à inclure. Les noms doivent suivre les conventions API.", "maxLength": 1000, "type": "string"}, "ids": {"description": "Liste séparée par des virgules des ID d'enregistrements à récupérer.", "maxLength": 2000, "type": "string"}, "page": {"default": 1, "description": "Numéro de page (à partir de 1)", "format": "int32", "maximum": 10000, "minimum": 1, "type": "integer"}, "page_token": {"description": "Jeton pour récupérer le lot suivant après 2000 enregistrements. Utiliser la valeur 'next_page_token' de la réponse précédente.", "maxLength": 500, "type": "string"}, "perPage": {"default": 200, "description": "Nombre d'enregistrements par page", "format": "int32", "maximum": 200, "minimum": 1, "type": "integer"}, "sort_by": {"default": "id", "description": "Champ de tri. Valeurs autorisées : id, Created_Time, Modified_Time.", "enum": ["id", "Created_Time", "Modified_Time"], "type": "string"}, "sort_order": {"default": "desc", "description": "Ordre de tri des enregistrements.", "enum": ["asc", "desc"], "type": "string"}}, "required": ["fields"], "type": "object"}}, "required": ["query_params", "path_variables"]}
      },
      {
        name: "ZohoCRM_getRelatedRecordsCount",
        description: "Récupère le nombre d'enregistrements liés pour un enregistrement parent spécifique. Prend en charge le filtrage par différents critères incluant l'état d'approbation, la catégorie et les filtres de champs.",
        input_schema: {"type": "object", "properties": {"body": {"description": "Corps de la requête contenant un tableau de spécifications de décompte de listes liées.", "properties": {"get_related_records_count": {"description": "Tableau de requêtes de décompte. Chaque élément spécifie une liste liée et des critères de filtrage optionnels.", "items": {"description": "Specifies a related list to count and optional filtering criteria.", "properties": {"params": {"description": "Paramètres de filtrage optionnels à appliquer avant le décompte.", "properties": {"approval_state": {"description": "Filtrer par état du workflow d'approbation.", "enum": ["approved"], "type": "string"}, "approved": {"description": "Filtrer pour ne compter que les enregistrements approuvés.", "type": "boolean"}, "category": {"description": "Filtrer par type de catégorie d'enregistrement.", "enum": ["link", "files"], "type": "string"}, "converted": {"description": "Filtrer pour ne compter que les enregistrements convertis (applicable aux Leads).", "type": "boolean"}, "filters": {"description": "Critères de filtrage par champ à appliquer avant le décompte.", "properties": {"comparator": {"description": "L'opérateur de comparaison à utiliser pour le filtrage.", "enum": ["equal"], "type": "string"}, "field": {"description": "Spécifie le champ sur lequel filtrer lors du décompte.", "properties": {"api_name": {"description": "Le nom API du champ sur lequel filtrer.", "maxLength": 100, "minLength": 1, "type": "string"}}, "required": ["api_name"], "type": "object"}, "value": {"description": "La valeur à comparer au champ.", "maxLength": 255, "minLength": 1, "type": "string"}}, "required": ["comparator", "field", "value"], "type": "object"}}, "required": ["filters"], "type": "object"}, "related_list": {"description": "Identifie une liste liée spécifique par son nom API et son identifiant unique.", "properties": {"api_name": {"description": "Le nom API de la liste liée (ex : 'Contacts', 'Deals', 'Tasks').", "maxLength": 100, "minLength": 1, "type": "string"}, "id": {"description": "L'identifiant unique de la définition de la liste liée.", "maxLength": 20, "minLength": 1, "type": "string"}}, "required": ["api_name", "id"], "type": "object"}}, "required": ["related_list"], "type": "object"}, "type": "array"}}, "required": ["get_related_records_count"], "type": "object"}, "path_variables": {"properties": {"moduleApiName": {"description": "Le nom API du module CRM contenant l'enregistrement parent (ex : 'Contacts', 'Leads', 'Deals', 'Accounts').", "maxLength": 100, "minLength": 1, "type": "string"}, "recordId": {"description": "L'identifiant unique de l'enregistrement parent. C'est généralement un ID numérique ou un UUID.", "maxLength": 50, "minLength": 1, "type": "string"}}, "required": ["moduleApiName", "recordId"], "type": "object"}}, "required": ["body", "path_variables"]}
      },
      {
        name: "ZohoCRM_getTimelines",
        description: "Récupère la chronologie d'un enregistrement.",
        input_schema: {"type": "object", "properties": {"path_variables": {"properties": {"module": {"description": "Le nom API du module (ex : Leads, Contacts, etc.)", "maxLength": 255, "type": "string"}, "recordId": {"description": "L'identifiant de l'enregistrement dont récupérer la chronologie", "maxLength": 255, "type": "string"}}, "required": ["module", "recordId"], "type": "object"}, "query_params": {"properties": {"filter": {"description": "Critères de filtrage de la chronologie", "maxLength": 255, "type": "string"}, "include": {"description": "Données supplémentaires à inclure", "maxLength": 255, "type": "string"}, "include_inner_details": {"description": "Inclure les détails internes", "maxLength": 255, "type": "string"}, "include_timeline_type": {"description": "Type de chronologie à inclure", "maxLength": 255, "type": "string"}, "page": {"description": "Numéro de page pour la pagination", "format": "int32", "type": "integer"}, "page_token": {"description": "Jeton de pagination", "maxLength": 255, "type": "string"}, "per_page": {"description": "Nombre d'enregistrements par page", "enum": [3], "format": "int32", "type": "integer"}, "sort_by": {"description": "Champ de tri de la chronologie", "enum": ["audited_time"], "type": "string"}, "sort_order": {"description": "Ordre de tri de la chronologie", "enum": ["asc", "desc"], "type": "string"}}, "required": [], "type": "object"}}, "required": ["path_variables"]}
      },
    ]
  },
]

export function getServerBySlug(slug: string): DocServer | undefined {
  return docServers.find(s => s.slug === slug)
}
