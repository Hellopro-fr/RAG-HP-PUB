//! account-service directory: users and groups (teams), read from
//! `GET {ACCOUNT_SERVICE_INTERNAL_URL}/internal/directory` with `X-Admin-Token`, cached in memory.
//!
//! On a refresh failure the last good copy keeps being served (a short account-service outage
//! must not lock everyone out); with no copy at all the call fails.

use std::sync::Arc;
use std::time::{Duration, Instant};

use serde::Deserialize;
use tokio::sync::RwLock;

use crate::error::{AppError, AppResult};

#[derive(Debug, Clone, Deserialize, PartialEq, Eq)]
pub struct DirUser {
    pub email: String,
    #[serde(default)]
    pub display_name: String,
    pub is_allowed: bool,
}

#[derive(Debug, Clone, Deserialize, PartialEq, Eq)]
pub struct DirGroup {
    pub id: String,
    pub name: String,
    #[serde(default)]
    pub description: String,
    #[serde(default)]
    pub members: Vec<String>,
}

#[derive(Debug, Clone, Default, Deserialize, PartialEq, Eq)]
pub struct Directory {
    #[serde(default)]
    pub users: Vec<DirUser>,
    #[serde(default)]
    pub groups: Vec<DirGroup>,
}

impl Directory {
    pub fn user(&self, email: &str) -> Option<&DirUser> {
        self.users
            .iter()
            .find(|u| u.email.eq_ignore_ascii_case(email))
    }

    /// Groups the user belongs to, in directory order (by name).
    pub fn teams_of(&self, email: &str) -> Vec<&DirGroup> {
        self.groups
            .iter()
            .filter(|g| g.members.iter().any(|m| m.eq_ignore_ascii_case(email)))
            .collect()
    }

    pub fn group(&self, id: &str) -> Option<&DirGroup> {
        self.groups.iter().find(|g| g.id == id)
    }
}

pub enum DirectoryClient {
    /// No account-service configured: nobody has teams.
    Disabled,
    /// Fixed directory (tests).
    Static(Arc<Directory>),
    Remote {
        http: reqwest::Client,
        url: String,
        token: String,
        ttl: Duration,
        cache: RwLock<Option<(Instant, Arc<Directory>)>>,
    },
}

impl DirectoryClient {
    pub fn remote(base_url: &str, token: &str, ttl: Duration) -> Self {
        DirectoryClient::Remote {
            http: reqwest::Client::builder()
                .timeout(Duration::from_secs(5))
                .build()
                .expect("reqwest client"),
            url: format!("{}/internal/directory", base_url.trim_end_matches('/')),
            token: token.to_string(),
            ttl,
            cache: RwLock::new(None),
        }
    }

    pub fn is_enabled(&self) -> bool {
        !matches!(self, DirectoryClient::Disabled)
    }

    /// The directory, from cache when fresh.
    pub async fn get(&self) -> AppResult<Arc<Directory>> {
        self.load(false).await
    }

    /// Bypass the cache (e.g. a user who just signed in for the first time).
    pub async fn refresh(&self) -> AppResult<Arc<Directory>> {
        self.load(true).await
    }

    async fn load(&self, force: bool) -> AppResult<Arc<Directory>> {
        let (http, url, token, ttl, cache) = match self {
            DirectoryClient::Disabled => return Ok(Arc::new(Directory::default())),
            DirectoryClient::Static(d) => return Ok(d.clone()),
            DirectoryClient::Remote {
                http,
                url,
                token,
                ttl,
                cache,
            } => (http, url, token, ttl, cache),
        };
        if !force
            && let Some((at, d)) = cache.read().await.as_ref()
            && at.elapsed() < *ttl
        {
            return Ok(d.clone());
        }
        let fetched = async {
            let res = http
                .get(url.as_str())
                .header("X-Admin-Token", token.as_str())
                .send()
                .await?
                .error_for_status()?;
            res.json::<Directory>().await
        }
        .await;
        match fetched {
            Ok(d) => {
                let d = Arc::new(d);
                *cache.write().await = Some((Instant::now(), d.clone()));
                Ok(d)
            }
            Err(e) => {
                if let Some((_, d)) = cache.read().await.as_ref() {
                    tracing::warn!(error = %e, "account-service directory refresh failed, serving the last copy");
                    return Ok(d.clone());
                }
                Err(AppError::Internal(anyhow::anyhow!(
                    "account-service directory unavailable: {e}"
                )))
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn lookups_are_case_insensitive_on_email() {
        let d: Directory = serde_json::from_value(serde_json::json!({
            "users": [{"email": "Ana@Example.com", "display_name": "Ana", "is_allowed": true}],
            "groups": [
                {"id": "g1", "name": "Catalogue", "members": ["ana@example.com"]},
                {"id": "g2", "name": "Prix", "members": []}
            ]
        }))
        .unwrap();
        assert!(d.user("ana@example.com").is_some());
        let teams: Vec<_> = d
            .teams_of("ANA@example.com")
            .iter()
            .map(|g| g.id.clone())
            .collect();
        assert_eq!(teams, vec!["g1"]);
        assert_eq!(d.group("g2").unwrap().name, "Prix");
    }
}
