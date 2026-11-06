//! Server-Sent Events (§6).
//!
//! `GET /api/projects/{id}/stream`: `id:` = seq, `event:` = type, `data:` = the stored event.
//! On connect: subscribe to the hub FIRST, replay from the table after `Last-Event-ID` (or
//! `?after=`), then forward live events, dropping any seq already sent. Gaps and lag are refilled
//! from the table, so a client never misses or duplicates an event. Keep-alive every 15 s.

use std::convert::Infallible;
use std::time::Duration;

use axum::extract::{Path, Query, State};
use axum::http::{HeaderMap, HeaderValue, header};
use axum::response::sse::{Event, KeepAlive, Sse};
use axum::response::{IntoResponse, Response};
use futures::StreamExt;
use tokio::sync::broadcast::error::RecvError;
use tokio::sync::mpsc;
use tokio_stream::wrappers::ReceiverStream;
use uuid::Uuid;

use super::dto::{GlobalStreamQuery, StreamQuery};
use crate::error::{AppError, AppResult};
use crate::metrics::SseGuard;
use crate::repository::{StoredEvent, reads};
use crate::state::AppState;

const KEEP_ALIVE: Duration = Duration::from_secs(15);

fn to_sse(ev: &StoredEvent, id: String) -> Event {
    let data = serde_json::to_string(ev).unwrap_or_else(|_| "{}".into());
    Event::default()
        .id(id)
        .event(ev.event_type.clone())
        .data(data)
}

fn sse_response(rx: mpsc::Receiver<Event>) -> Response {
    let stream = ReceiverStream::new(rx).map(Ok::<_, Infallible>);
    let mut res = Sse::new(stream)
        .keep_alive(KeepAlive::new().interval(KEEP_ALIVE).text("keep-alive"))
        .into_response();
    let h = res.headers_mut();
    // Tell proxies (nginx, Caddy) not to buffer or transform the stream.
    h.insert("x-accel-buffering", HeaderValue::from_static("no"));
    h.insert(
        header::CACHE_CONTROL,
        HeaderValue::from_static("no-cache, no-transform"),
    );
    res
}

#[utoipa::path(get, path = "/api/projects/{id}/stream", tag = "realtime", params(("id" = Uuid, Path), StreamQuery),
    responses((status = 200, description = "text/event-stream of StoredEvent", content_type = "text/event-stream")))]
pub async fn project_stream(
    State(st): State<AppState>,
    Path(project_id): Path<Uuid>,
    Query(q): Query<StreamQuery>,
    headers: HeaderMap,
) -> AppResult<Response> {
    let resume = headers
        .get("last-event-id")
        .and_then(|v| v.to_str().ok())
        .and_then(|v| v.trim().parse::<i64>().ok())
        .or(q.after);
    let rx_hub = st.hub.subscribe();
    let current = {
        let mut conn = st.pool.acquire().await?;
        reads::project_seq(&mut conn, project_id)
            .await?
            .ok_or_else(|| AppError::not_found("project"))?
    };
    // Without a resume point, start live from "now".
    let start = resume.unwrap_or(current).clamp(0, current.max(0));
    let (tx, rx) = mpsc::channel(256);
    tokio::spawn(pump_project(st, project_id, start, rx_hub, tx));
    Ok(sse_response(rx))
}

async fn pump_project(
    st: AppState,
    project_id: Uuid,
    mut last: i64,
    mut hub: tokio::sync::broadcast::Receiver<std::sync::Arc<StoredEvent>>,
    tx: mpsc::Sender<Event>,
) {
    let _guard = SseGuard::new(st.metrics.clone());
    if refill(&st, project_id, &mut last, &tx).await.is_err() {
        return;
    }
    loop {
        tokio::select! {
            _ = tx.closed() => return,
            msg = hub.recv() => match msg {
                Ok(ev) if ev.project_id == project_id => {
                    if ev.seq <= last {
                        continue; // already sent by the replay
                    }
                    if ev.seq == last + 1 {
                        if tx.send(to_sse(&ev, ev.seq.to_string())).await.is_err() {
                            return;
                        }
                        last = ev.seq;
                    } else if refill(&st, project_id, &mut last, &tx).await.is_err() {
                        return;
                    }
                }
                Ok(_) => {}
                Err(RecvError::Lagged(_)) => {
                    if refill(&st, project_id, &mut last, &tx).await.is_err() {
                        return;
                    }
                }
                Err(RecvError::Closed) => return,
            }
        }
    }
}

/// Send every event after `last` from the table, in order.
async fn refill(
    st: &AppState,
    project_id: Uuid,
    last: &mut i64,
    tx: &mpsc::Sender<Event>,
) -> Result<(), ()> {
    loop {
        let batch = {
            let mut conn = st.pool.acquire().await.map_err(|_| ())?;
            reads::events_after(&mut conn, project_id, *last, 500)
                .await
                .map_err(|_| ())?
        };
        let full = batch.len() == 500;
        for ev in batch {
            tx.send(to_sse(&ev, ev.seq.to_string()))
                .await
                .map_err(|_| ())?;
            *last = ev.seq;
        }
        if !full {
            return Ok(());
        }
    }
}

/// `GET /api/stream?topics=questions,reviews`: cross-project inbox stream. No resume: clients
/// refetch their inbox on reconnect (per-project seqs cannot form one global cursor).
#[utoipa::path(get, path = "/api/stream", tag = "realtime", params(GlobalStreamQuery),
    responses((status = 200, description = "text/event-stream of StoredEvent", content_type = "text/event-stream")))]
pub async fn global_stream(
    State(st): State<AppState>,
    Query(q): Query<GlobalStreamQuery>,
) -> AppResult<Response> {
    let topics = q.topics.unwrap_or_else(|| "questions,reviews".into());
    let mut prefixes = Vec::new();
    for t in topics.split(',').map(str::trim).filter(|t| !t.is_empty()) {
        match t {
            "questions" => prefixes.push("question."),
            "reviews" => prefixes.push("review."),
            other => {
                return Err(AppError::BadRequest(format!(
                    "unknown topic {other:?} (questions, reviews)"
                )));
            }
        }
    }
    let mut hub = st.hub.subscribe();
    let (tx, rx) = mpsc::channel(256);
    let metrics = st.metrics.clone();
    tokio::spawn(async move {
        let _guard = SseGuard::new(metrics);
        loop {
            tokio::select! {
                _ = tx.closed() => return,
                msg = hub.recv() => match msg {
                    Ok(ev) if prefixes.iter().any(|p| ev.event_type.starts_with(p)) => {
                        let id = format!("{}:{}", ev.project_id, ev.seq);
                        if tx.send(to_sse(&ev, id)).await.is_err() {
                            return;
                        }
                    }
                    Ok(_) => {}
                    // Tell the client to refetch: a lagged inbox stream may have dropped items.
                    Err(RecvError::Lagged(_)) => {
                        if tx.send(Event::default().event("resync").data("{}")).await.is_err() {
                            return;
                        }
                    }
                    Err(RecvError::Closed) => return,
                }
            }
        }
    });
    Ok(sse_response(rx))
}
