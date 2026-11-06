//! Shared application state handed to every presentation-layer handler.

use std::sync::Arc;

use sqlx::PgPool;

use crate::config::Config;
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
}

impl AppState {
    pub fn new(pool: PgPool, cfg: Config) -> Self {
        Self {
            pool,
            cfg: Arc::new(cfg),
            hub: Hub::new(4096),
            metrics: Arc::new(Metrics::default()),
            limiter: Arc::new(RateLimiter::default()),
            notifier: Arc::new(PgNotifier),
        }
    }
}
