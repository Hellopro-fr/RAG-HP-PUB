//! Background sweeper (§7): every `SWEEP_INTERVAL_SECS`, expire unpaused leases past
//! `expires_at` — each through the decider in its own transaction — and purge stale idempotency
//! keys (> 24 h) and sessions. TODO(phase-2): re-queue test runs past `deadline_at`.

use std::time::Duration;

use super::{commands, now};
use crate::error::AppResult;
use crate::repository::store;
use crate::state::AppState;

pub async fn run(st: AppState) {
    let mut tick = tokio::time::interval(Duration::from_secs(st.cfg.sweep_interval_secs.max(1)));
    tick.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Delay);
    loop {
        tick.tick().await;
        if let Err(e) = sweep_once(&st).await {
            tracing::warn!(error = %e, "sweep failed");
        }
    }
}

/// One sweep. Returns how many leases expired.
pub async fn sweep_once(st: &AppState) -> AppResult<usize> {
    let ids = {
        let mut conn = st.pool.acquire().await?;
        store::expired_leases(&mut conn, now(), 200).await?
    };
    let mut expired = 0;
    for task_id in ids {
        let mut tx = st.pool.begin().await?;
        match commands::expire_lease(&mut tx, st, task_id).await {
            Ok(true) => {
                tx.commit().await?;
                expired += 1;
                tracing::info!(%task_id, "lease expired");
            }
            Ok(false) => tx.rollback().await?,
            Err(e) => {
                tracing::warn!(%task_id, error = %e, "lease expiry failed");
                tx.rollback().await?;
            }
        }
    }
    let mut conn = st.pool.acquire().await?;
    store::purge(&mut conn, now()).await?;
    Ok(expired)
}
