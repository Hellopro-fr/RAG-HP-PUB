//! Pure event application on the task aggregate.

use crate::event::DomainEvent;
use crate::model::{Attempt, Lease, ReviewVerdict, TaskSnapshot};

/// Build the aggregate from its `task.created` event. Returns `None` for any other event.
pub fn create(event: &DomainEvent) -> Option<TaskSnapshot> {
    match event {
        DomainEvent::TaskCreated {
            task_id,
            project_id,
            title,
            spec_id,
            spec_version,
            priority,
            state,
            ..
        } => Some(TaskSnapshot {
            id: *task_id,
            project_id: *project_id,
            title: title.clone(),
            priority: *priority,
            state: *state,
            version: 1,
            spec_id: *spec_id,
            spec_version: *spec_version,
            spec_outdated: false,
            preferred_actor_id: None,
            preferred_until: None,
            attempt_count: 0,
            rejection_count: 0,
            lease: None,
            attempt: None,
        }),
        _ => None,
    }
}

/// Apply one event to the aggregate. Events for other tasks leave it unchanged.
pub fn apply(mut task: TaskSnapshot, event: &DomainEvent) -> TaskSnapshot {
    if event.task_id() != Some(task.id) {
        return task;
    }
    match event {
        DomainEvent::TaskCreated { .. } => {
            if let Some(fresh) = create(event) {
                task = fresh;
            }
        }
        DomainEvent::TaskUpdated {
            title, priority, ..
        } => {
            if let Some(t) = title {
                task.title = t.clone();
            }
            if let Some(p) = priority {
                task.priority = *p;
            }
            task.version += 1;
        }
        DomainEvent::TaskStateChanged {
            to,
            preferred_actor_id,
            preferred_until,
            submission,
            ..
        } => {
            task.state = *to;
            task.preferred_actor_id = *preferred_actor_id;
            task.preferred_until = *preferred_until;
            if let (Some(sub), Some(att)) = (submission, task.attempt.as_mut()) {
                att.commit_sha = Some(sub.commit_sha.clone());
                att.branch = sub.branch.clone();
            }
            task.version += 1;
        }
        DomainEvent::TaskSpecOutdated { .. } => {
            task.spec_outdated = true;
            task.version += 1;
        }
        DomainEvent::TaskRepinned { spec_version, .. } => {
            task.spec_version = *spec_version;
            task.spec_outdated = false;
            task.version += 1;
        }
        DomainEvent::LeaseClaimed {
            actor_id,
            kind,
            token_hash,
            expires_at,
            attempt,
            ..
        } => {
            task.lease = Some(Lease {
                actor_id: *actor_id,
                kind: *kind,
                token_hash: token_hash.clone(),
                expires_at: *expires_at,
                paused: false,
            });
            if let Some(a) = attempt {
                task.attempt = Some(Attempt {
                    id: a.attempt_id,
                    n: a.n,
                    actor_id: *actor_id,
                    actor_model: a.actor_model.clone(),
                    commit_sha: None,
                    branch: None,
                });
                task.attempt_count = a.n;
            }
        }
        DomainEvent::LeaseReleased { .. } | DomainEvent::LeaseExpired { .. } => {
            task.lease = None;
        }
        DomainEvent::TestRequested {
            commit_sha, branch, ..
        } => {
            if let Some(l) = task.lease.as_mut() {
                l.paused = true;
            }
            if let Some(a) = task.attempt.as_mut() {
                a.commit_sha = Some(commit_sha.clone());
                a.branch = branch.clone();
            }
        }
        DomainEvent::TestCompleted {
            passed,
            protected_path_violation,
            resume_expires_at,
            ..
        } => {
            // A failed run hands the task back to its holder with a fresh TTL.
            if (!*passed || *protected_path_violation)
                && let Some(l) = task.lease.as_mut()
            {
                l.paused = false;
                if let Some(at) = resume_expires_at {
                    l.expires_at = *at;
                }
            }
        }
        DomainEvent::ReviewSubmitted { verdict, .. } => {
            if *verdict == ReviewVerdict::ChangesRequested {
                task.rejection_count += 1;
            }
        }
        DomainEvent::AttemptEnded { .. } => {
            task.attempt = None;
        }
        DomainEvent::TaskLinkAdded { .. }
        | DomainEvent::ActivityReported { .. }
        | DomainEvent::QuestionAsked { .. }
        | DomainEvent::QuestionAnswered { .. }
        | DomainEvent::SpecVersionProposed { .. }
        | DomainEvent::SpecVersionApproved { .. } => {}
    }
    task
}

/// Apply a sequence of events.
pub fn apply_all(task: TaskSnapshot, events: &[DomainEvent]) -> TaskSnapshot {
    events.iter().fold(task, apply)
}
