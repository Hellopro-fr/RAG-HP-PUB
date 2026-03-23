use serde::{Deserialize, Serialize};
use tonic::transport::Channel;
use tracing::error;

use super::proto::graph_normalization::graph_normalization_service_client::GraphNormalizationServiceClient;
use super::proto::graph_normalization::{NormalizeQuantityRequest, NormalizeRangeRequest};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct NormResult {
    pub valeur_canonique: f64,
    pub unite_canonique: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct NormRangeResult {
    pub valeur_min_canonique: f64,
    pub valeur_max_canonique: f64,
    pub unite_canonique: String,
}

#[derive(Clone)]
pub struct GraphNormalizationClient {
    client: GraphNormalizationServiceClient<Channel>,
}

impl GraphNormalizationClient {
    pub async fn new(url: &str) -> Result<Self, Box<dyn std::error::Error>> {
        let endpoint = format!("http://{}", url);
        let channel = Channel::from_shared(endpoint)?.connect().await?;
        Ok(Self {
            client: GraphNormalizationServiceClient::new(channel),
        })
    }

    pub async fn normalize_quantity(
        &self,
        label: &str,
        unit: Option<&str>,
        value: &str,
    ) -> Option<NormResult> {
        let request = tonic::Request::new(NormalizeQuantityRequest {
            label: label.to_string(),
            unit: unit.unwrap_or("").to_string(),
            value: value.to_string(),
            data_type: "numeric".to_string(),
        });

        match self.client.clone().normalize_quantity(request).await {
            Ok(response) => {
                let resp = response.into_inner();
                if resp.success {
                    Some(NormResult {
                        valeur_canonique: resp.canonical_value,
                        unite_canonique: resp.canonical_unit,
                    })
                } else {
                    None
                }
            }
            Err(e) => {
                error!("Normalization Error: {}", e);
                None
            }
        }
    }

    pub async fn normalize_range(
        &self,
        label: &str,
        unit: Option<&str>,
        min_value: f64,
        max_value: f64,
    ) -> Option<NormRangeResult> {
        let request = tonic::Request::new(NormalizeRangeRequest {
            label: label.to_string(),
            unit: unit.unwrap_or("").to_string(),
            min_value,
            max_value,
            data_type: String::new(),
        });

        match self.client.clone().normalize_range(request).await {
            Ok(response) => {
                let resp = response.into_inner();
                if resp.success {
                    Some(NormRangeResult {
                        valeur_min_canonique: resp.canonical_min,
                        valeur_max_canonique: resp.canonical_max,
                        unite_canonique: resp.canonical_unit,
                    })
                } else {
                    None
                }
            }
            Err(e) => {
                error!("Range Normalization Error: {}", e);
                None
            }
        }
    }
}
