use prost_types::Struct as ProstStruct;
use serde_json::Value;
use tonic::transport::Channel;
use tracing::error;

use super::proto::graph_database::graph_database_service_client::GraphDatabaseServiceClient;
use super::proto::graph_database::{ExecuteCypherRequest, GetGraphSchemaRequest};

#[derive(Clone)]
pub struct GraphDatabaseClient {
    client: GraphDatabaseServiceClient<Channel>,
}

impl GraphDatabaseClient {
    pub async fn new(url: &str) -> Result<Self, Box<dyn std::error::Error>> {
        let endpoint = format!("http://{}", url);
        let channel = Channel::from_shared(endpoint)?.connect().await?;
        Ok(Self {
            client: GraphDatabaseServiceClient::new(channel),
        })
    }

    /// Convert serde_json::Value to prost_types::Struct
    fn json_to_prost_struct(val: &Value) -> Option<ProstStruct> {
        if let Value::Object(map) = val {
            let fields = map
                .iter()
                .map(|(k, v)| (k.clone(), Self::json_to_prost_value(v)))
                .collect();
            Some(ProstStruct { fields })
        } else {
            None
        }
    }

    /// Convert serde_json::Value to prost_types::Value
    fn json_to_prost_value(val: &Value) -> prost_types::Value {
        use prost_types::value::Kind;
        let kind = match val {
            Value::Null => Kind::NullValue(0),
            Value::Bool(b) => Kind::BoolValue(*b),
            Value::Number(n) => Kind::NumberValue(n.as_f64().unwrap_or(0.0)),
            Value::String(s) => Kind::StringValue(s.clone()),
            Value::Array(arr) => Kind::ListValue(prost_types::ListValue {
                values: arr.iter().map(Self::json_to_prost_value).collect(),
            }),
            Value::Object(map) => {
                let fields = map
                    .iter()
                    .map(|(k, v)| (k.clone(), Self::json_to_prost_value(v)))
                    .collect();
                Kind::StructValue(ProstStruct { fields })
            }
        };
        prost_types::Value { kind: Some(kind) }
    }

    /// Convert prost_types::Value to serde_json::Value
    fn prost_value_to_json(val: &prost_types::Value) -> Value {
        use prost_types::value::Kind;
        match &val.kind {
            Some(Kind::NullValue(_)) => Value::Null,
            Some(Kind::BoolValue(b)) => Value::Bool(*b),
            Some(Kind::NumberValue(n)) => {
                serde_json::Number::from_f64(*n)
                    .map(Value::Number)
                    .unwrap_or(Value::Null)
            }
            Some(Kind::StringValue(s)) => Value::String(s.clone()),
            Some(Kind::ListValue(list)) => {
                Value::Array(list.values.iter().map(Self::prost_value_to_json).collect())
            }
            Some(Kind::StructValue(s)) => Self::prost_struct_to_json(s),
            None => Value::Null,
        }
    }

    /// Convert prost_types::Struct to serde_json::Value
    pub fn prost_struct_to_json(s: &ProstStruct) -> Value {
        let map: serde_json::Map<String, Value> = s
            .fields
            .iter()
            .map(|(k, v)| (k.clone(), Self::prost_value_to_json(v)))
            .collect();
        Value::Object(map)
    }

    pub async fn execute_cypher(
        &self,
        query: &str,
        params: Option<&Value>,
        read_only: bool,
    ) -> (bool, Vec<Value>, String) {
        let parameters = params.and_then(Self::json_to_prost_struct);

        let request = tonic::Request::new(ExecuteCypherRequest {
            cypher_query: query.to_string(),
            parameters,
            read_only,
        });

        match self.client.clone().execute_raw_cypher(request).await {
            Ok(response) => {
                let resp = response.into_inner();
                let raw_results: Vec<Value> = resp
                    .results
                    .iter()
                    .map(Self::prost_struct_to_json)
                    .collect();

                // Unwrap __json_results__ wrapper format (matches Python client behavior)
                let results = if let Some(first) = raw_results.first() {
                    if let Some(json_str) = first.get("__json_results__").and_then(|v| v.as_str()) {
                        serde_json::from_str::<Vec<Value>>(json_str).unwrap_or(raw_results)
                    } else {
                        raw_results
                    }
                } else {
                    raw_results
                };

                (resp.success, results, resp.error_message)
            }
            Err(e) => {
                error!("Graph DB Error: {}", e);
                (false, vec![], e.to_string())
            }
        }
    }

    pub async fn get_graph_schema(&self, include_properties: bool) -> String {
        let request = tonic::Request::new(GetGraphSchemaRequest {
            include_properties,
            include_indexes: false,
        });

        match self.client.clone().get_graph_schema(request).await {
            Ok(response) => response.into_inner().schema_text,
            Err(e) => {
                error!("Graph Schema Error: {}", e);
                String::new()
            }
        }
    }
}
