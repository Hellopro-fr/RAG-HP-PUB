//! One background `PgListener` per process: on each notification it loads the new events from the
//! table (after the last broadcast seq of that project) and fans them out through a tokio
//! broadcast channel. Subscribers that lag refill themselves from the table.

use std::collections::HashMap;
use std::sync::Arc;
use std::time::Duration;

use sqlx::PgPool;
use sqlx::postgres::PgListener;
use tokio::sync::broadcast;
use uuid::Uuid;

use super::{CHANNEL, parse_payload};
use crate::repository::{StoredEvent, reads};

#[derive(Clone)]
pub struct Hub {
    tx: broadcast::Sender<Arc<StoredEvent>>,
}

impl Hub {
    pub fn new(capacity: usize) -> Self {
        let (tx, _) = broadcast::channel(capacity);
        Self { tx }
    }

    pub fn subscribe(&self) -> broadcast::Receiver<Arc<StoredEvent>> {
        self.tx.subscribe()
    }

    /// Run forever: listen, forward, reconnect on error.
    pub async fn run(self, pool: PgPool) {
        let mut last_sent: HashMap<Uuid, i64> = HashMap::new();
        loop {
            if let Err(e) = self.listen(&pool, &mut last_sent).await {
                tracing::warn!(error = %e, "realtime listener failed; reconnecting");
            }
            tokio::time::sleep(Duration::from_millis(500)).await;
        }
    }

    async fn listen(
        &self,
        pool: &PgPool,
        last_sent: &mut HashMap<Uuid, i64>,
    ) -> anyhow::Result<()> {
        let mut listener = PgListener::connect_with(pool).await?;
        listener.listen(CHANNEL).await?;
        tracing::info!("realtime listener connected");
        // Notifications may have been missed while disconnected: catch up every known project.
        self.catch_up(pool, last_sent).await?;
        loop {
            match listener.try_recv().await? {
                Some(n) => {
                    let Some((project_id, first, last)) = parse_payload(n.payload()) else {
                        tracing::warn!(payload = n.payload(), "ignoring malformed notification");
                        continue;
                    };
                    let from = *last_sent.entry(project_id).or_insert(first - 1);
                    if last > from {
                        self.forward(pool, project_id, from, last, last_sent)
                            .await?;
                    }
                }
                None => {
                    // Connection lost; sqlx reconnects on the next call.
                    tracing::warn!("realtime listener connection lost");
                    self.catch_up(pool, last_sent).await?;
                }
            }
        }
    }

    async fn catch_up(
        &self,
        pool: &PgPool,
        last_sent: &mut HashMap<Uuid, i64>,
    ) -> anyhow::Result<()> {
        let projects: Vec<(Uuid, i64)> = last_sent.iter().map(|(p, s)| (*p, *s)).collect();
        for (project_id, from) in projects {
            let mut conn = pool.acquire().await?;
            if let Some(seq) = reads::project_seq(&mut conn, project_id).await?
                && seq > from
            {
                drop(conn);
                self.forward(pool, project_id, from, seq, last_sent).await?;
            }
        }
        Ok(())
    }

    async fn forward(
        &self,
        pool: &PgPool,
        project_id: Uuid,
        after: i64,
        up_to: i64,
        last_sent: &mut HashMap<Uuid, i64>,
    ) -> anyhow::Result<()> {
        let mut conn = pool.acquire().await?;
        let events = reads::events_between(&mut conn, project_id, after, up_to).await?;
        for ev in events {
            let seq = ev.seq;
            // No receivers is fine: nobody is watching right now.
            let _ = self.tx.send(Arc::new(ev));
            last_sent.insert(project_id, seq);
        }
        Ok(())
    }
}
