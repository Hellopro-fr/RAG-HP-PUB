//! `atb-server` — Agent Task Board backend.
//!
//! ```text
//! atb-server serve                         run the HTTP server (REST, SSE, /mcp), hub, sweeper
//! atb-server migrate                       apply migrations (DATABASE_OWNER_URL or DATABASE_URL)
//! atb-server dump-openapi                  print the OpenAPI document (no database needed)
//! atb-server rebuild-check <project_id>    AC-1.8: replay the log and diff the projections
//! atb-server create-actor <kind> <name> <roles> [model] [gateway_subject]
//!                                          create an agent/verifier and print its token once
//! ```

use std::time::Duration;

use anyhow::{Context, bail};
use atb_server::service::auth::{self, NewActorInput, NewActorKind};
use atb_server::service::{rebuild, sweeper};
use atb_server::{AppState, Config, MIGRATOR, api};
use sqlx::postgres::PgPoolOptions;
use tracing_subscriber::EnvFilter;

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    tracing_subscriber::fmt()
        .json()
        .with_current_span(true)
        .with_env_filter(
            EnvFilter::try_from_default_env().unwrap_or_else(|_| EnvFilter::new("info")),
        )
        .init();
    let args: Vec<String> = std::env::args().skip(1).collect();
    match args.first().map(String::as_str) {
        Some("dump-openapi") => {
            println!("{}", api::openapi::json());
            Ok(())
        }
        Some("migrate") => migrate().await,
        Some("rebuild-check") => {
            let project = args.get(1).context("usage: rebuild-check <project_id>")?;
            let cfg = Config::from_env()?;
            let pool = PgPoolOptions::new()
                .max_connections(2)
                .connect(&cfg.database_url)
                .await?;
            let report = rebuild::check_project(&pool, project.parse()?)
                .await
                .map_err(|e| anyhow::anyhow!("{}", e.message()))?;
            println!("{}", serde_json::to_string_pretty(&report)?);
            if !report.ok {
                bail!("projections differ from the event log");
            }
            Ok(())
        }
        Some("create-actor") => create_actor(&args[1..]).await,
        Some("serve") | None => serve().await,
        Some(other) => bail!("unknown command {other:?}"),
    }
}

async fn migrate() -> anyhow::Result<()> {
    let cfg = Config::from_env()?;
    let url = cfg
        .database_owner_url
        .as_deref()
        .unwrap_or(&cfg.database_url);
    let pool = PgPoolOptions::new().max_connections(1).connect(url).await?;
    MIGRATOR.run(&pool).await?;
    tracing::info!("migrations applied");
    Ok(())
}

async fn create_actor(args: &[String]) -> anyhow::Result<()> {
    let usage = "usage: create-actor <agent|verifier> <name> <roles,comma,separated> [model|-] [gateway_subject]";
    let kind = match args.first().map(String::as_str) {
        Some("agent") => NewActorKind::Agent,
        Some("verifier") => NewActorKind::Verifier,
        _ => bail!(usage),
    };
    let name = args.get(1).context(usage)?.clone();
    let roles = args
        .get(2)
        .map(|r| {
            r.split(',')
                .map(|s| s.trim().to_string())
                .filter(|s| !s.is_empty())
                .collect()
        })
        .unwrap_or_default();
    let cfg = Config::from_env()?;
    let pool = PgPoolOptions::new()
        .max_connections(1)
        .connect(&cfg.database_url)
        .await?;
    let created = auth::create_actor_unchecked(
        &pool,
        NewActorInput {
            kind,
            name,
            model: args.get(3).cloned().filter(|m| !m.is_empty() && m != "-"),
            roles,
            login: None,
            password: None,
            gateway_subject: args.get(4).cloned(),
        },
    )
    .await
    .map_err(|e| anyhow::anyhow!("{}", e.message()))?;
    println!("{}", serde_json::to_string(&created)?);
    Ok(())
}

async fn serve() -> anyhow::Result<()> {
    let cfg = Config::from_env()?;
    if cfg.notifier == atb_server::config::NotifierKind::Redis {
        bail!("NOTIFIER=redis arrives in phase 3; use NOTIFIER=pg");
    }
    let pool = PgPoolOptions::new()
        .max_connections(cfg.db_max_connections)
        .acquire_timeout(Duration::from_secs(5))
        .connect(&cfg.database_url)
        .await
        .context("connecting to DATABASE_URL")?;
    if let (Ok(login), Ok(password)) = (
        std::env::var("ATB_BOOTSTRAP_ADMIN_LOGIN"),
        std::env::var("ATB_BOOTSTRAP_ADMIN_PASSWORD"),
    ) && !login.trim().is_empty()
    {
        match auth::bootstrap_admin(&pool, login.trim(), &password).await {
            Ok(true) => tracing::info!(login = login.trim(), "bootstrap admin created"),
            Ok(false) => {}
            Err(e) => tracing::warn!(error = %e.message(), "bootstrap admin not created"),
        }
    }
    let bind = cfg.bind_addr;
    let st = AppState::new(pool.clone(), cfg);
    tokio::spawn(st.hub.clone().run(pool));
    tokio::spawn(sweeper::run(st.clone()));
    let app = api::router(st);
    let listener = tokio::net::TcpListener::bind(bind).await?;
    tracing::info!(%bind, "agent task board listening");
    axum::serve(listener, app)
        .with_graceful_shutdown(async {
            let _ = tokio::signal::ctrl_c().await;
        })
        .await?;
    Ok(())
}
