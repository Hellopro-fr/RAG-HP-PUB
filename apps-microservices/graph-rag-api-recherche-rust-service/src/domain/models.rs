use serde::{Deserialize, Serialize};
use serde_json::Value;
use utoipa::ToSchema;

// ================================
// Base normalizer: trim whitespace on string deserialization
// ================================

fn trim_option_string<'de, D>(deserializer: D) -> Result<Option<String>, D::Error>
where
    D: serde::Deserializer<'de>,
{
    let opt = Option::<String>::deserialize(deserializer)?;
    Ok(opt.map(|s| s.trim().to_string()).filter(|s| !s.is_empty()))
}

// ================================
// Query Models (RAG)
// ================================

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
pub struct QueryRequest {
    pub query: String,
    pub strategy: Option<String>,
    #[serde(default)]
    pub use_reranking: bool,
    pub top_k: Option<i32>,
    pub threshold: Option<f64>,
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
pub struct QueryResponse {
    pub answer: String,
    pub sources: Vec<Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub strategy_used: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub processing_time: Option<f64>,
}

// ================================
// Admin Models
// ================================

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
pub struct CypherQueryRequest {
    pub query: String,
    #[serde(default)]
    pub params: Option<Value>,
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
pub struct CypherQueryResponse {
    pub success: bool,
    pub data: Value,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
pub struct CategorieCountResponse {
    pub id_categorie: String,
    pub count: i64,
}

// ================================
// Scoring Options
// ================================

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema, Default)]
pub struct ScoringOptions {
    pub v_blocked: Option<f64>,
    pub v_different: Option<f64>,
    pub z_unmatched: Option<f64>,
    pub e_unmatched: Option<f64>,
    pub g_unknown_score: Option<f64>,
    pub c_unknown_score: Option<f64>,
    pub t_unmatched: Option<f64>,
    pub absolute_threshold: Option<f64>,
    pub relative_tolerance: Option<f64>,
    pub max_per_supplier_primary: Option<i32>,
    pub max_per_supplier_extended: Option<i32>,
    pub score_step: Option<f64>,
    pub diversity_lambda: Option<f64>,
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema, Default)]
pub struct MatchingOptionsScore {
    pub critique: Option<i32>,
    pub secondaire: Option<i32>,
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema, Default)]
pub struct MatchingOptions {
    pub score: Option<MatchingOptionsScore>,
}

// ================================
// Reranking Options
// ================================

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
pub struct RerankingOptions {
    pub use_rerank: bool,
    pub top_k: i32,
    #[serde(default)]
    pub parcours: Option<String>,
    #[serde(default)]
    pub id_prompt: Option<i32>,
}

// ================================
// Constraint / Caracteristique
// ================================

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
pub struct Constraint {
    pub id_caracteristique: Value, // Can be string or int
    pub valeurs_cibles: Option<Value>,  // Can be list of strings or dict {min, max, exact}
    pub valeurs_bloquantes: Option<Value>, // Same
    pub unite: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
pub struct MatchingCaracteristique {
    pub id_caracteristique: Value,
    pub valeurs_cibles: Option<Value>,
    pub valeurs_bloquantes: Option<Value>,
    pub unite: Option<String>,
    pub poids_caracteristique: Option<String>,
    pub poids_question: Option<i32>,
}

// ================================
// Metadonnee Utilisateurs
// ================================

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
pub struct MetadonneUtilisateurs {
    pub pays: Option<String>,
    pub cp: Option<String>,
    pub id_pays: Option<Value>,
    pub typologie: Option<Value>,
}

// ================================
// Complex Filter Request (V1 flow)
// ================================

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
pub struct ComplexFilterRequest {
    pub ids: std::collections::HashMap<String, Vec<Constraint>>,
    #[serde(default = "default_top_k")]
    pub top_k: i32,
    pub output_fields: Option<Vec<String>>,
    pub id_categorie: Option<Value>,
    #[serde(default = "default_blocked_val")]
    pub blocked_val: f64,
    #[serde(default = "default_different_val")]
    pub different_val: f64,
}

fn default_top_k() -> i32 { 15 }
fn default_blocked_val() -> f64 { -2.0 }
fn default_different_val() -> f64 { -0.3 }

// ================================
// Filter Caracteristique Request
// ================================

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
pub struct FilterCaracteristiqueRequest {
    pub liste_caracteristique: Vec<MatchingCaracteristique>,
    #[serde(default = "default_top_k")]
    pub top_k: i32,
    pub id_categorie: Option<Value>,
    pub options: Option<MatchingOptions>,
}

// ================================
// Matching Payload
// ================================

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
pub struct MatchingPayload {
    pub liste_caracteristique: Vec<MatchingCaracteristique>,
    #[serde(default = "default_top_k")]
    pub top_k: i32,
    pub id_categorie: Option<Value>,
    pub options: Option<MatchingOptions>,
    pub champs_sortie: Option<Vec<String>>,
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
pub struct MatchingPayloadIdProduit {
    pub liste_caracteristique: Vec<MatchingCaracteristique>,
    #[serde(default = "default_top_k")]
    pub top_k: i32,
    pub id_categorie: Option<Value>,
    pub id_produit: Option<Value>,
    pub options: Option<MatchingOptions>,
    pub champs_sortie: Option<Vec<String>>,
    pub metadonnee_utilisateurs: Option<MetadonneUtilisateurs>,
    pub scoring: Option<ScoringOptions>,
    pub rerank: Option<RerankingOptions>,
}

impl MatchingPayloadIdProduit {
    pub fn get_scoring(&self) -> ScoringOptions {
        self.scoring.clone().unwrap_or_default()
    }
}

// ================================
// CaracteristiqueMatching (output)
// ================================

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
pub struct CaracteristiqueMatching {
    pub statut_matching: i32,
    pub id_caracteristique: i64,
    pub type_caracteristique: i32,
    pub valeur: Option<String>,
    pub valeur_min: Option<String>,
    pub valeur_max: Option<String>,
    pub unite: Option<String>,
    pub id_valeur: Vec<i64>,
    pub poids: i32,
    pub bareme: f64,
    pub poids_question: i32,
}

// ================================
// Produit (output product)
// ================================

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
pub struct Produit {
    pub rang: i32,
    pub id_produit: String,
    pub score: f64,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub caracteristique: Option<Vec<CaracteristiqueMatching>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub info_produit: Option<Value>,
    #[serde(default = "default_one")]
    pub coeff_geo: f64,
    #[serde(default = "default_one")]
    pub coeff_type_frns: f64,
    #[serde(default = "default_one")]
    pub coeff_etat_score: f64,
    #[serde(default)]
    pub coeff_caracteristique: f64,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub llm_response: Option<Value>,
}

fn default_one() -> f64 { 1.0 }

// ================================
// Scored Product (simple filter response)
// ================================

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
pub struct ScoredProduct {
    #[serde(flatten)]
    pub data: Value,
    pub score: f64,
    pub details: Vec<Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub info: Option<Value>,
}

// ================================
// Result Product (complex filter response)
// ================================

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
pub struct ResultProduct {
    pub data: Vec<ScoredProduct>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub info: Option<Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub top_p: Option<Vec<ScoredProduct>>,
}

// ================================
// Matching Response
// ================================

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
pub struct MatchingResponse {
    pub top_produit: Vec<Produit>,
    pub liste_produit: Vec<Produit>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub ecarts: Option<Vec<Produit>>,
    #[serde(default)]
    pub temps_de_traitement: f64,
}

// ================================
// Fournisseur Geo Response
// ================================

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
pub struct PaysCouverture {
    pub id_pays: String,
    pub nom_pays: String,
    pub couvre_partiel: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
pub struct DepartementCouverture {
    pub id_dept: String,
    pub nom_dept: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
pub struct FournisseurGeoResponse {
    #[serde(default)]
    pub pays: Vec<PaysCouverture>,
    #[serde(default)]
    pub departements: Vec<DepartementCouverture>,
}

// ================================
// Node Models
// ================================

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
pub struct NodeUpdateRequest {
    pub properties: Value,
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
pub struct NodeResponse {
    pub success: bool,
    pub data: Option<Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
pub struct SchemaResponse {
    pub schema: String,
}

// ================================
// Product Characteristics Response
// ================================

#[derive(Debug, Clone, Serialize, Deserialize, ToSchema)]
pub struct ProductCaracteristiquesResponse {
    pub id_produit: String,
    pub caracteristiques: Vec<Value>,
}

// ================================
// RAG State (internal, not exposed)
// ================================

#[derive(Debug, Clone)]
pub struct RagState {
    pub query: String,
    pub strategy: String,
    pub entities: Vec<String>,
    pub vector_results: Vec<Value>,
    pub graph_results: Vec<Value>,
    pub merged_results: Vec<Value>,
    pub reranked_results: Vec<Value>,
    pub answer: String,
    pub iteration: usize,
}

impl RagState {
    pub fn new(query: &str) -> Self {
        Self {
            query: query.to_string(),
            strategy: String::new(),
            entities: vec![],
            vector_results: vec![],
            graph_results: vec![],
            merged_results: vec![],
            reranked_results: vec![],
            answer: String::new(),
            iteration: 0,
        }
    }
}
