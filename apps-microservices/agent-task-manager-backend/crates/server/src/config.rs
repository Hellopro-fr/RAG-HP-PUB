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
    /// account-service as seen by this server (token exchange, introspection, directory).
    /// `None` disables HelloPro sign-in and teams.
    pub account_internal_url: Option<String>,
    /// account-service as seen by the browser (`/authorize`). Defaults to the internal URL.
    pub account_public_url: Option<String>,
    /// account-service `INTERNAL_ADMIN_TOKEN`, sent as `X-Admin-Token` to read the directory.
    pub account_admin_token: Option<String>,
    /// OAuth2 client registered in account-service for this board.
    pub oauth_client_id: Option<String>,
    pub oauth_client_secret: Option<String>,
    /// Public base URL of this board (redirect URI = `{public_url}/api/auth/sso/callback`).
    pub public_url: Option<String>,
    pub directory_ttl_secs: u64,
    /// Local login/password. Defaults to on only when HelloPro sign-in is not configured.
    pub password_login: bool,
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

fn parse_opt_bool(name: &str) -> anyhow::Result<Option<bool>> {
    var(name)
        .map(|raw| {
            raw.trim()
                .parse::<bool>()
                .map_err(|e| anyhow::anyhow!("{name}={raw:?} is invalid: {e}"))
        })
        .transpose()
}

impl Config {
    /// HelloPro sign-in needs the internal URL, the client id/secret and this board's URL.
    pub fn sso_enabled(&self) -> bool {
        self.account_internal_url.is_some()
            && self.oauth_client_id.is_some()
            && self.oauth_client_secret.is_some()
            && self.public_url.is_some()
    }

    fn with_password_login_default(mut self, explicit: Option<bool>) -> Self {
        self.password_login = explicit.unwrap_or(!self.sso_enabled());
        self
    }

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
            account_internal_url: var("ACCOUNT_SERVICE_INTERNAL_URL"),
            account_public_url: var("ACCOUNT_SERVICE_PUBLIC_URL"),
            account_admin_token: var("ACCOUNT_SERVICE_ADMIN_TOKEN"),
            oauth_client_id: var("ATB_OAUTH_CLIENT_ID"),
            oauth_client_secret: var("ATB_OAUTH_CLIENT_SECRET"),
            public_url: var("ATB_PUBLIC_URL"),
            directory_ttl_secs: parse("DIRECTORY_TTL_SECS", 30)?,
            password_login: false,
        }
        .with_password_login_default(parse_opt_bool("PASSWORD_LOGIN")?))
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
            account_internal_url: None,
            account_public_url: None,
            account_admin_token: None,
            oauth_client_id: None,
            oauth_client_secret: None,
            public_url: None,
            directory_ttl_secs: 30,
            password_login: true,
        }
    }
}
