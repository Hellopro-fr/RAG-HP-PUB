use reqwest::Client;
use serde_json::{json, Value};
use std::collections::HashMap;
use std::time::Duration;
use tracing::{error, warn};

use crate::config::SETTINGS;

// API endpoints (mirrors Python's hellopro_api_client.py)
const HELLOPRO_VIEW_URL: &str = "https://api.hellopro.fr/api/hp/view/index.php";
const HELLOPRO_CARAC_URL: &str = "https://api.hellopro.fr/api/v2/index.php";

/// Map of Etat IDs to human-readable labels (mirrors Python's ETAT_SOCIETE_MAP).
pub fn etat_societe_map() -> HashMap<&'static str, &'static str> {
    let mut m = HashMap::new();
    m.insert("1", "Client");
    m.insert("2", "Pause");
    m.insert("3", "Prospects");
    m
}

/// HelloPro API HTTP client, mirroring Python's hellopro_api_client.
pub struct HelloProApiClient {
    client: Client,
    token: String,
}

impl HelloProApiClient {
    pub fn new() -> Self {
        let client = Client::builder()
            .timeout(Duration::from_secs(30))
            .connect_timeout(Duration::from_secs(10))
            .build()
            .expect("Failed to build reqwest client");

        Self {
            client,
            token: SETTINGS.hellopro_api_bearer_token.clone(),
        }
    }

    fn auth_headers(&self) -> reqwest::header::HeaderMap {
        let mut headers = reqwest::header::HeaderMap::new();
        if !self.token.is_empty() {
            headers.insert(
                reqwest::header::AUTHORIZATION,
                format!("Bearer {}", self.token).parse().unwrap(),
            );
        } else {
            warn!("HELLOPRO_API_BEARER_TOKEN is not set, requests may fail");
        }
        headers.insert(
            reqwest::header::CONTENT_TYPE,
            "application/json".parse().unwrap(),
        );
        headers
    }

    /// Fetch product info for multiple products in a category.
    /// POST https://api.hellopro.fr/api/hp/view/index.php
    /// Returns dict of product info keyed by id_produit.
    pub async fn fetch_products_info(
        &self,
        id_categorie: &str,
        id_produits: &[String],
    ) -> HashMap<String, Value> {
        if id_produits.is_empty() {
            return HashMap::new();
        }

        let payload = json!({
            "etape": "get_info_produit",
            "scrapping": 1,
            "action": "get",
            "data": {
                "id_categorie": id_categorie,
                "id_produits": id_produits,
            }
        });

        match self.client.post(HELLOPRO_VIEW_URL)
            .headers(self.auth_headers())
            .json(&payload)
            .send()
            .await
        {
            Ok(response) => {
                if response.status().is_success() {
                    match response.json::<Value>().await {
                        Ok(data) => {
                            // Response format: { "items": { "id_produit": { ... }, ... } }
                            if let Some(items) = data.get("items").and_then(|v| v.as_object()) {
                                return items
                                    .iter()
                                    .map(|(k, v)| (k.clone(), v.clone()))
                                    .collect();
                            }
                            return HashMap::new();
                        }
                        Err(e) => error!("Failed to parse products info response: {}", e),
                    }
                } else {
                    warn!("Products info API returned: {}", response.status());
                }
            }
            Err(e) => error!("HelloPro fetch_products_info error: {}", e),
        }
        HashMap::new()
    }

    /// Fetch characteristics for a single product.
    /// POST https://api.hellopro.fr/api/v2/index.php
    /// Returns list of characteristic dicts.
    pub async fn fetch_product_caracteristiques(
        &self,
        id_produit: &str,
    ) -> Vec<Value> {
        let payload = json!({
            "etape": "caracterisation",
            "field": "produit",
            "action": "get",
            "data": {
                "id_produit": id_produit.to_string(),
            }
        });

        match self.client.post(HELLOPRO_CARAC_URL)
            .headers(self.auth_headers())
            .json(&payload)
            .send()
            .await
        {
            Ok(response) => {
                if response.status().is_success() {
                    match response.json::<Value>().await {
                        Ok(data) => {
                            // Response format: { "code": 200, "response": [ ... ] }
                            if let Some(arr) = data.get("response").and_then(|v| v.as_array()) {
                                return arr.clone();
                            }
                            return vec![];
                        }
                        Err(e) => error!("Failed to parse product caracs: {}", e),
                    }
                }
            }
            Err(e) => error!("HelloPro fetch_product_caracteristiques error for {}: {}", id_produit, e),
        }
        vec![]
    }

    /// Fetch characteristics for all products in parallel.
    pub async fn fetch_all_product_caracteristiques(
        &self,
        id_produits: &[String],
    ) -> HashMap<String, Vec<Value>> {
        if id_produits.is_empty() {
            return HashMap::new();
        }

        let mut handles = vec![];

        for id in id_produits {
            let id = id.clone();
            let client = self.client.clone();
            let headers = self.auth_headers();

            let payload = json!({
                "etape": "caracterisation",
                "field": "produit",
                "action": "get",
                "data": {
                    "id_produit": id.to_string(),
                }
            });

            handles.push(tokio::spawn(async move {
                match client.post(HELLOPRO_CARAC_URL)
                    .headers(headers)
                    .json(&payload)
                    .send()
                    .await
                {
                    Ok(response) if response.status().is_success() => {
                        let data: Value = response.json().await.unwrap_or(Value::Null);
                        let caracs = data
                            .get("response")
                            .and_then(|v| v.as_array())
                            .cloned()
                            .unwrap_or_default();
                        (id, caracs)
                    }
                    _ => (id, vec![]),
                }
            }));
        }

        let mut result = HashMap::new();
        for handle in handles {
            if let Ok((id, caracs)) = handle.await {
                result.insert(id, caracs);
            }
        }
        result
    }

    /// Fetch category characteristics definitions.
    /// POST https://api.hellopro.fr/api/v2/index.php
    pub async fn fetch_category_caracteristiques(
        &self,
        id_categorie: &str,
    ) -> Vec<Value> {
        let payload = json!({
            "etape": "caracteristique",
            "field": "final",
            "action": "get",
            "data": {
                "id_categorie": id_categorie.to_string(),
            }
        });

        match self.client.post(HELLOPRO_CARAC_URL)
            .headers(self.auth_headers())
            .json(&payload)
            .send()
            .await
        {
            Ok(response) => {
                if response.status().is_success() {
                    match response.json::<Value>().await {
                        Ok(data) => {
                            // Response format: { "code": 200, "response": [ ... ] }
                            if let Some(arr) = data.get("response").and_then(|v| v.as_array()) {
                                return arr.clone();
                            }
                            return vec![];
                        }
                        Err(e) => error!("Failed to parse category caracs: {}", e),
                    }
                }
            }
            Err(e) => error!("HelloPro fetch_category_caracteristiques error for category {}: {}", id_categorie, e),
        }
        vec![]
    }

    /// Fetch prompt content from HelloPro API.
    /// POST https://api.hellopro.fr/api/v2/index.php
    pub async fn fetch_prompt(&self, id_prompt: &str) -> Option<Value> {
        let payload = json!({
            "etape": "prompt",
            "field": "info",
            "action": "get",
            "data": {
                "id_prompt": id_prompt.to_string(),
            }
        });

        match self.client.post(HELLOPRO_CARAC_URL)
            .headers(self.auth_headers())
            .json(&payload)
            .send()
            .await
        {
            Ok(response) => {
                if response.status().is_success() {
                    match response.json::<Value>().await {
                        Ok(data) => {
                            // Response format: { "code": 200, "response": { ... } }
                            return data.get("response").cloned();
                        }
                        Err(e) => error!("Failed to parse prompt response: {}", e),
                    }
                } else {
                    warn!("Prompt API returned: {}", response.status());
                }
            }
            Err(e) => error!("HelloPro fetch_prompt error for id_prompt {}: {}", id_prompt, e),
        }
        None
    }
}

/// Global singleton
pub static HELLOPRO_CLIENT: once_cell::sync::Lazy<HelloProApiClient> =
    once_cell::sync::Lazy::new(HelloProApiClient::new);
