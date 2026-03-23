use reqwest::Client;
use serde_json::Value;
use std::collections::HashMap;
use std::time::Duration;
use tracing::{error, warn};

use crate::config::SETTINGS;

/// Map of Etat IDs to human-readable labels (mirrors Python's ETAT_SOCIETE_MAP).
pub fn etat_societe_map() -> HashMap<&'static str, &'static str> {
    let mut m = HashMap::new();
    m.insert("1", "Client");
    m.insert("2", "Prospect");
    m.insert("3", "Ancien client");
    m.insert("4", "Suspect");
    m
}

/// HelloPro API HTTP client, mirroring Python's hellopro_api_client.
pub struct HelloProApiClient {
    client: Client,
    base_url: String,
    token: String,
}

impl HelloProApiClient {
    pub fn new() -> Self {
        let client = Client::builder()
            .timeout(Duration::from_secs(30))
            .build()
            .expect("Failed to build reqwest client");

        Self {
            client,
            base_url: "https://hellopro.fr/api".to_string(),
            token: SETTINGS.hellopro_api_bearer_token.clone(),
        }
    }

    fn auth_headers(&self) -> reqwest::header::HeaderMap {
        let mut headers = reqwest::header::HeaderMap::new();
        headers.insert(
            reqwest::header::AUTHORIZATION,
            format!("Bearer {}", self.token).parse().unwrap(),
        );
        headers.insert(
            reqwest::header::CONTENT_TYPE,
            "application/json".parse().unwrap(),
        );
        headers
    }

    /// Fetch product info for multiple products in a category.
    pub async fn fetch_products_info(
        &self,
        id_categorie: &str,
        id_produits: &[String],
    ) -> HashMap<String, Value> {
        let url = format!(
            "{}/recherche/categories/{}/produits",
            self.base_url, id_categorie
        );

        let body = serde_json::json!({
            "id_produits": id_produits
        });

        match self.client.post(&url)
            .headers(self.auth_headers())
            .json(&body)
            .send()
            .await
        {
            Ok(response) => {
                if response.status().is_success() {
                    match response.json::<Value>().await {
                        Ok(json) => {
                            let mut result = HashMap::new();
                            if let Some(products) = json.as_array() {
                                for product in products {
                                    if let Some(id) = product.get("produit")
                                        .and_then(|p| p.get("id_produit"))
                                        .and_then(|id| id.as_str().or_else(|| id.as_i64().map(|_| "")))
                                    {
                                        let key = product.get("produit")
                                            .and_then(|p| p.get("id_produit"))
                                            .map(|id| id.to_string().trim_matches('"').to_string())
                                            .unwrap_or_default();
                                        result.insert(key, product.clone());
                                    }
                                }
                            } else if let Some(obj) = json.as_object() {
                                for (k, v) in obj {
                                    result.insert(k.clone(), v.clone());
                                }
                            }
                            return result;
                        }
                        Err(e) => error!("Failed to parse products info response: {}", e),
                    }
                } else {
                    warn!("Products info API returned: {}", response.status());
                }
            }
            Err(e) => error!("Products info API error: {}", e),
        }
        HashMap::new()
    }

    /// Fetch characteristics for a single product.
    pub async fn fetch_product_caracteristiques(
        &self,
        id_produit: &str,
    ) -> Vec<Value> {
        let url = format!(
            "{}/recherche/produits/{}/caracteristiques",
            self.base_url, id_produit
        );

        match self.client.get(&url)
            .headers(self.auth_headers())
            .send()
            .await
        {
            Ok(response) => {
                if response.status().is_success() {
                    match response.json::<Vec<Value>>().await {
                        Ok(caracs) => return caracs,
                        Err(e) => error!("Failed to parse product caracs: {}", e),
                    }
                }
            }
            Err(e) => error!("Product caracs API error: {}", e),
        }
        vec![]
    }

    /// Fetch characteristics for all products in parallel.
    pub async fn fetch_all_product_caracteristiques(
        &self,
        id_produits: &[String],
    ) -> HashMap<String, Vec<Value>> {
        let mut handles = vec![];

        for id in id_produits {
            let id = id.clone();
            let url = format!(
                "{}/recherche/produits/{}/caracteristiques",
                self.base_url, id
            );
            let client = self.client.clone();
            let headers = self.auth_headers();

            handles.push(tokio::spawn(async move {
                match client.get(&url).headers(headers).send().await {
                    Ok(response) if response.status().is_success() => {
                        let caracs: Vec<Value> = response.json().await.unwrap_or_default();
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
    pub async fn fetch_category_caracteristiques(
        &self,
        id_categorie: &str,
    ) -> Vec<Value> {
        let url = format!(
            "{}/recherche/categories/{}/caracteristiques",
            self.base_url, id_categorie
        );

        match self.client.get(&url)
            .headers(self.auth_headers())
            .send()
            .await
        {
            Ok(response) => {
                if response.status().is_success() {
                    match response.json::<Vec<Value>>().await {
                        Ok(caracs) => return caracs,
                        Err(e) => error!("Failed to parse category caracs: {}", e),
                    }
                }
            }
            Err(e) => error!("Category caracs API error: {}", e),
        }
        vec![]
    }

    /// Fetch prompt content from HelloPro API.
    pub async fn fetch_prompt(&self, id_prompt: &str) -> Option<Value> {
        let url = format!(
            "{}/recherche/prompts/{}",
            self.base_url, id_prompt
        );

        match self.client.get(&url)
            .headers(self.auth_headers())
            .send()
            .await
        {
            Ok(response) => {
                if response.status().is_success() {
                    match response.json::<Value>().await {
                        Ok(data) => return Some(data),
                        Err(e) => error!("Failed to parse prompt response: {}", e),
                    }
                } else {
                    warn!("Prompt API returned: {}", response.status());
                }
            }
            Err(e) => error!("Prompt API error: {}", e),
        }
        None
    }
}

/// Global singleton
pub static HELLOPRO_CLIENT: once_cell::sync::Lazy<HelloProApiClient> =
    once_cell::sync::Lazy::new(HelloProApiClient::new);
