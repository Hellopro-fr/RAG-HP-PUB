//! Configuration from environment variables (§12). Project workflow values override the
//! lease/grace defaults.

use std::net::SocketAddr;

use anyhow::{Context, bail};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum NotifierKind {
    Pg,
    /// TODO(phase-3): Redis notifier.
    Redis,
}

#[derive(Debug, Clone)]
pub struct Config {
    /// Runtime role (atb_app).
    pub database_url: String,
    /// Owner role, used only by `migrate`. Falls back to `database_url`.
    pub database_owner_url: Option<String>,
    pub bind_addr: SocketAddr,
    pub lease_ttl_secs: i64,
    pub preferred_grace_secs: i64,
    pub sweep_interval_secs: u64,
    pub max_reports_per_min: u32,
    pub max_waits_per_min: u32,
    pub notifier: NotifierKind,
    pub cors_origins: Vec<String>,
    /// Shared secret sent by the MCP gateway as `X-Agent-Gateway-Secret`. `None` disables
    /// gateway identity headers entirely.
    pub gateway_shared_secret: Option<String>,
    /// Hostnames accepted by the MCP transport's `Host` validation.
    pub mcp_allowed_hosts: Vec<String>,
    pub session_ttl_hours: i64,
    pub cookie_secure: bool,
    pub db_max_connections: u32,
}

fn var(name: &str) -> Option<String> {
    std::env::var(name).ok().filter(|v| !v.trim().is_empty())
}

fn parse<T: std::str::FromStr>(name: &str, default: T) -> anyhow::Result<T>
where
    T::Err: std::fmt::Display,
{
    match var(name) {
        None => Ok(default),
        Some(raw) => raw
            .trim()
            .parse()
            .map_err(|e| anyhow::anyhow!("{name}={raw:?} is invalid: {e}")),
    }
}

fn list(name: &str) -> Vec<String> {
    var(name)
        .map(|v| {
            v.split(',')
                .map(|s| s.trim().to_string())
                .filter(|s| !s.is_empty())
                .collect()
        })
        .unwrap_or_default()
}

impl Config {
    pub fn from_env() -> anyhow::Result<Self> {
        let database_url = var("DATABASE_URL").context("DATABASE_URL is required")?;
        let notifier = match var("NOTIFIER").as_deref().unwrap_or("pg") {
            "pg" => NotifierKind::Pg,
            "redis" => NotifierKind::Redis,
            other => bail!("NOTIFIER must be pg or redis, got {other:?}"),
        };
        let mut mcp_allowed_hosts = list("MCP_ALLOWED_HOSTS");
        if mcp_allowed_hosts.is_empty() {
            mcp_allowed_hosts = vec!["localhost".into(), "127.0.0.1".into(), "::1".into()];
        }
        Ok(Self {
            database_url,
            database_owner_url: var("DATABASE_OWNER_URL"),
            bind_addr: parse("BIND_ADDR", SocketAddr::from(([0, 0, 0, 0], 8621)))?,
            lease_ttl_secs: parse("LEASE_TTL_SECS", 600)?,
            preferred_grace_secs: parse("PREFERRED_GRACE_SECS", 120)?,
            sweep_interval_secs: parse("SWEEP_INTERVAL_SECS", 5)?,
            max_reports_per_min: parse("MAX_REPORTS_PER_MIN", 60)?,
            max_waits_per_min: parse("MAX_WAITS_PER_MIN", 120)?,
            notifier,
            cors_origins: list("CORS_ORIGINS"),
            gateway_shared_secret: var("GATEWAY_SHARED_SECRET"),
            mcp_allowed_hosts,
            session_ttl_hours: parse("SESSION_TTL_HOURS", 12)?,
            cookie_secure: parse("COOKIE_SECURE", false)?,
            db_max_connections: parse("DB_MAX_CONNECTIONS", 30)?,
        })
    }

    /// Defaults for tests: everything except the database URL.
    pub fn for_tests(database_url: String) -> Self {
        Self {
            database_url,
            database_owner_url: None,
            bind_addr: SocketAddr::from(([127, 0, 0, 1], 0)),
            lease_ttl_secs: 600,
            preferred_grace_secs: 120,
            sweep_interval_secs: 1,
            max_reports_per_min: 600,
            max_waits_per_min: 600,
            notifier: NotifierKind::Pg,
            cors_origins: vec![],
            gateway_shared_secret: Some("test-gateway-secret".into()),
            mcp_allowed_hosts: vec!["localhost".into(), "127.0.0.1".into()],
            session_ttl_hours: 12,
            cookie_secure: false,
            db_max_connections: 40,
        }
    }
}
