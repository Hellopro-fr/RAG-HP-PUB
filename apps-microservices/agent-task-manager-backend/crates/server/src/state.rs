//! Shared application state handed to every presentation-layer handler.

use std::sync::Arc;

use sqlx::PgPool;

use crate::config::Config;
use crate::directory::DirectoryClient;
use crate::metrics::Metrics;
use crate::realtime::{Hub, Notifier, PgNotifier};
use crate::service::ratelimit::RateLimiter;

#[derive(Clone)]
pub struct AppState {
    pub pool: PgPool,
    pub cfg: Arc<Config>,
    pub hub: Hub,
    pub metrics: Arc<Metrics>,
    pub limiter: Arc<RateLimiter>,
    pub notifier: Arc<dyn Notifier>,
    /// account-service users and teams.
    pub directory: Arc<DirectoryClient>,
}

impl AppState {
    pub fn new(pool: PgPool, cfg: Config) -> Self {
        let directory = match (&cfg.account_internal_url, &cfg.account_admin_token) {
            (Some(url), Some(token)) => DirectoryClient::remote(
                url,
                token,
                std::time::Duration::from_secs(cfg.directory_ttl_secs),
            ),
            _ => DirectoryClient::Disabled,
        };
        Self {
            pool,
            cfg: Arc::new(cfg),
            hub: Hub::new(4096),
            metrics: Arc::new(Metrics::default()),
            limiter: Arc::new(RateLimiter::default()),
            notifier: Arc::new(PgNotifier),
            directory: Arc::new(directory),
        }
    }
}

impl AppState {
    /// Replace the directory (tests use a fixed one).
    pub fn with_directory(mut self, directory: DirectoryClient) -> Self {
        self.directory = Arc::new(directory);
        self
    }
}
