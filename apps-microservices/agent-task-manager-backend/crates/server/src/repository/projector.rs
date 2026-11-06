//! DomainEvent → projection rows. The ONLY writer of projection tables, shared by the live
//! command path and the rebuild check (AC-1.8). It must be a pure function of (event, meta):
//! every timestamp comes from `meta.at` (the event's `created_at`), never from `now()`.

use atb_core::{DomainEvent, ReviewVerdict};
use sqlx::PgConnection;
use time::OffsetDateTime;
use uuid::Uuid;

pub struct Meta<'a> {
    pub project_id: Uuid,
    pub actor_id: Uuid,
    pub at: OffsetDateTime,
    pub trace_id: Option<&'a str>,
}

pub async fn project(
    conn: &mut PgConnection,
    ev: &DomainEvent,
    m: &Meta<'_>,
) -> Result<(), sqlx::Error> {
    match ev {
        DomainEvent::TaskCreated {
            task_id,
            project_id,
            title,
            spec_id,
            spec_version,
            parent_id,
            priority,
            state,
            created_by,
        } => {
            sqlx::query!(
                r#"INSERT INTO tasks (id, project_id, parent_id, title, spec_id, spec_version, state,
                       priority, version, spec_outdated, attempt_count, rejection_count, created_by,
                       created_at, updated_at)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 1, false, 0, 0, $9, $10, $10)"#,
                task_id,
                project_id,
                *parent_id,
                title,
                spec_id,
                spec_version,
                state.as_str(),
                priority,
                created_by,
                m.at,
            )
            .execute(&mut *conn)
            .await?;
        }
        DomainEvent::TaskUpdated {
            task_id,
            title,
            priority,
        } => {
            sqlx::query!(
                r#"UPDATE tasks SET title = COALESCE($2, title), priority = COALESCE($3, priority),
                       version = version + 1, updated_at = $4
                   WHERE id = $1"#,
                task_id,
                title.as_deref(),
                *priority,
                m.at,
            )
            .execute(&mut *conn)
            .await?;
        }
        DomainEvent::TaskStateChanged {
            task_id,
            to,
            preferred_actor_id,
            preferred_until,
            submission,
            ..
        } => {
            sqlx::query!(
                r#"UPDATE tasks SET state = $2, preferred_actor_id = $3, preferred_until = $4,
                       version = version + 1, updated_at = $5
                   WHERE id = $1"#,
                task_id,
                to.as_str(),
                *preferred_actor_id,
                *preferred_until,
                m.at,
            )
            .execute(&mut *conn)
            .await?;
            if let Some(sub) = submission {
                sqlx::query!(
                    r#"UPDATE attempts SET commit_sha = $2, branch = $3, updated_at = $4
                       WHERE task_id = $1 AND ended_at IS NULL"#,
                    task_id,
                    sub.commit_sha,
                    sub.branch.as_deref(),
                    m.at,
                )
                .execute(&mut *conn)
                .await?;
            }
        }
        DomainEvent::TaskLinkAdded {
            from_id,
            to_id,
            kind,
        } => {
            sqlx::query!(
                r#"INSERT INTO task_links (from_id, to_id, kind, created_at) VALUES ($1, $2, $3, $4)
                   ON CONFLICT DO NOTHING"#,
                from_id,
                to_id,
                kind.as_str(),
                m.at,
            )
            .execute(&mut *conn)
            .await?;
        }
        DomainEvent::TaskSpecOutdated { task_id, .. } => {
            sqlx::query!(
                r#"UPDATE tasks SET spec_outdated = true, version = version + 1, updated_at = $2
                   WHERE id = $1"#,
                task_id,
                m.at,
            )
            .execute(&mut *conn)
            .await?;
        }
        DomainEvent::TaskRepinned {
            task_id,
            spec_version,
        } => {
            sqlx::query!(
                r#"UPDATE tasks SET spec_version = $2, spec_outdated = false, version = version + 1,
                       updated_at = $3
                   WHERE id = $1"#,
                task_id,
                spec_version,
                m.at,
            )
            .execute(&mut *conn)
            .await?;
        }
        DomainEvent::SpecVersionProposed {
            spec_id,
            project_id,
            title,
            version,
            body_md,
            acceptance_criteria,
            protected_paths,
            test_ref,
            author_id,
        } => {
            sqlx::query!(
                r#"INSERT INTO specs (id, project_id, title, approved_version, created_at, updated_at)
                   VALUES ($1, $2, $3, NULL, $4, $4)
                   ON CONFLICT (id) DO UPDATE SET title = EXCLUDED.title, updated_at = EXCLUDED.updated_at"#,
                spec_id,
                project_id,
                title,
                m.at,
            )
            .execute(&mut *conn)
            .await?;
            sqlx::query!(
                r#"INSERT INTO spec_versions (spec_id, version, body_md, acceptance_criteria,
                       protected_paths, test_ref, status, author_id, created_at, updated_at)
                   VALUES ($1, $2, $3, $4, $5, $6, 'draft', $7, $8, $8)"#,
                spec_id,
                version,
                body_md,
                acceptance_criteria,
                protected_paths,
                test_ref.as_deref(),
                author_id,
                m.at,
            )
            .execute(&mut *conn)
            .await?;
        }
        DomainEvent::SpecVersionApproved {
            spec_id,
            version,
            approved_by,
            approved_at,
        } => {
            sqlx::query!(
                r#"UPDATE spec_versions SET status = 'superseded', updated_at = $2
                   WHERE spec_id = $1 AND status = 'approved'"#,
                spec_id,
                m.at,
            )
            .execute(&mut *conn)
            .await?;
            sqlx::query!(
                r#"UPDATE spec_versions SET status = 'approved', approved_by = $3, approved_at = $4,
                       updated_at = $5
                   WHERE spec_id = $1 AND version = $2"#,
                spec_id,
                version,
                approved_by,
                approved_at,
                m.at,
            )
            .execute(&mut *conn)
            .await?;
            sqlx::query!(
                "UPDATE specs SET approved_version = $2, updated_at = $3 WHERE id = $1",
                spec_id,
                version,
                m.at,
            )
            .execute(&mut *conn)
            .await?;
        }
        DomainEvent::LeaseClaimed {
            task_id,
            actor_id,
            kind,
            token_hash,
            expires_at,
            attempt,
        } => {
            sqlx::query!(
                r#"INSERT INTO leases (task_id, actor_id, kind, token_hash, expires_at, paused,
                       last_heartbeat_at, created_at, updated_at)
                   VALUES ($1, $2, $3, $4, $5, false, $6, $6, $6)"#,
                task_id,
                actor_id,
                kind.as_str(),
                token_hash,
                expires_at,
                m.at,
            )
            .execute(&mut *conn)
            .await?;
            if let Some(a) = attempt {
                sqlx::query!(
                    r#"INSERT INTO attempts (id, task_id, n, actor_id, actor_model, started_at,
                           trace_id, created_at, updated_at)
                       VALUES ($1, $2, $3, $4, $5, $6, $7, $6, $6)"#,
                    a.attempt_id,
                    task_id,
                    a.n,
                    actor_id,
                    a.actor_model.as_deref(),
                    m.at,
                    m.trace_id,
                )
                .execute(&mut *conn)
                .await?;
                sqlx::query!(
                    "UPDATE tasks SET attempt_count = $2, updated_at = $3 WHERE id = $1",
                    task_id,
                    a.n,
                    m.at,
                )
                .execute(&mut *conn)
                .await?;
            }
        }
        DomainEvent::LeaseReleased { task_id, .. } | DomainEvent::LeaseExpired { task_id, .. } => {
            sqlx::query!("DELETE FROM leases WHERE task_id = $1", task_id)
                .execute(&mut *conn)
                .await?;
        }
        DomainEvent::ActivityReported { .. } => {
            // Activities live only in the event log (timeline, presence rate).
        }
        DomainEvent::QuestionAsked {
            question_id,
            task_id,
            asked_by,
            body,
            options,
            blocking,
        } => {
            sqlx::query!(
                r#"INSERT INTO questions (id, task_id, asked_by, body, options, blocking, status,
                       created_at, updated_at)
                   VALUES ($1, $2, $3, $4, $5, $6, 'open', $7, $7)"#,
                question_id,
                task_id,
                asked_by,
                body,
                options.clone(),
                blocking,
                m.at,
            )
            .execute(&mut *conn)
            .await?;
        }
        DomainEvent::QuestionAnswered {
            question_id,
            answered_by,
            answer,
            answered_at,
            ..
        } => {
            sqlx::query!(
                r#"UPDATE questions SET status = 'answered', answered_by = $2, answer = $3,
                       answered_at = $4, updated_at = $5
                   WHERE id = $1"#,
                question_id,
                answered_by,
                answer,
                answered_at,
                m.at,
            )
            .execute(&mut *conn)
            .await?;
        }
        DomainEvent::TestRequested {
            task_id,
            attempt_id,
            commit_sha,
            branch,
            ..
        } => {
            // TODO(phase-2): insert the queued row into test_runs.
            sqlx::query!(
                "UPDATE leases SET paused = true, updated_at = $2 WHERE task_id = $1",
                task_id,
                m.at,
            )
            .execute(&mut *conn)
            .await?;
            sqlx::query!(
                "UPDATE attempts SET commit_sha = $2, branch = $3, updated_at = $4 WHERE id = $1",
                attempt_id,
                commit_sha,
                branch.as_deref(),
                m.at,
            )
            .execute(&mut *conn)
            .await?;
        }
        DomainEvent::TestCompleted {
            task_id,
            passed,
            protected_path_violation,
            resume_expires_at,
            ..
        } => {
            // TODO(phase-2): record the result in test_runs.
            if !*passed || *protected_path_violation {
                sqlx::query!(
                    r#"UPDATE leases SET paused = false,
                           expires_at = COALESCE($2, expires_at), updated_at = $3
                       WHERE task_id = $1"#,
                    task_id,
                    *resume_expires_at,
                    m.at,
                )
                .execute(&mut *conn)
                .await?;
            }
        }
        DomainEvent::ReviewSubmitted {
            task_id, verdict, ..
        } => {
            // TODO(phase-2): insert the review row.
            if *verdict == ReviewVerdict::ChangesRequested {
                sqlx::query!(
                    r#"UPDATE tasks SET rejection_count = rejection_count + 1, updated_at = $2
                       WHERE id = $1"#,
                    task_id,
                    m.at,
                )
                .execute(&mut *conn)
                .await?;
            }
        }
        DomainEvent::AttemptEnded {
            attempt_id,
            outcome,
            handoff_note,
            ..
        } => {
            sqlx::query!(
                r#"UPDATE attempts SET ended_at = $2, outcome = $3, handoff_note = $4, updated_at = $2
                   WHERE id = $1"#,
                attempt_id,
                m.at,
                outcome.as_str(),
                handoff_note.as_deref(),
            )
            .execute(&mut *conn)
            .await?;
        }
    }
    Ok(())
}
