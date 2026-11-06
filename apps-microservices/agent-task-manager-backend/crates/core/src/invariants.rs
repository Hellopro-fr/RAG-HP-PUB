//! Structural invariants of the task aggregate. A legal state never violates them; the proptest
//! drives random command sequences through `decide` + `apply` and checks them after every step.

use crate::model::{LeaseKind, TaskSnapshot, TaskState};

/// Returns the first violated invariant, if any.
pub fn check(task: &TaskSnapshot) -> Result<(), String> {
    let lease = task.lease.as_ref();
    match task.state {
        TaskState::Working => {
            let l = lease.ok_or("working without a lease")?;
            if l.kind != LeaseKind::Work || l.paused {
                return Err("working needs an active work lease".into());
            }
            let a = task
                .attempt
                .as_ref()
                .ok_or("working without an open attempt")?;
            if a.actor_id != l.actor_id {
                return Err("work lease holder differs from the attempt actor".into());
            }
        }
        TaskState::Testing => {
            let l = lease.ok_or("testing without a lease")?;
            if l.kind != LeaseKind::Work || !l.paused {
                return Err("testing needs a paused work lease".into());
            }
            let a = task.attempt.as_ref().ok_or("testing without an attempt")?;
            if a.commit_sha.is_none() {
                return Err("testing without a commit".into());
            }
        }
        TaskState::InReview => {
            if lease.is_some_and(|l| l.kind != LeaseKind::Review) {
                return Err("in_review with a non-review lease".into());
            }
            let a = task
                .attempt
                .as_ref()
                .ok_or("in_review without an attempt")?;
            if a.commit_sha.is_none() {
                return Err("in_review without a commit".into());
            }
            if lease.is_some_and(|l| l.actor_id == a.actor_id) {
                return Err("implementer holds its own review lease".into());
            }
        }
        TaskState::Draft
        | TaskState::Ready
        | TaskState::InputRequired
        | TaskState::Done
        | TaskState::Failed
        | TaskState::Cancelled => {
            if lease.is_some() {
                return Err(format!("{} must not hold a lease", task.state.as_str()));
            }
            if task.attempt.is_some() {
                return Err(format!(
                    "{} must not have an open attempt",
                    task.state.as_str()
                ));
            }
        }
    }
    if task.preferred_actor_id.is_some() && task.state != TaskState::Ready {
        return Err("claim preference outside ready".into());
    }
    if task.preferred_actor_id.is_some() != task.preferred_until.is_some() {
        return Err("preferred_actor_id and preferred_until must be set together".into());
    }
    if task.rejection_count < 0 || task.attempt_count < 0 {
        return Err("negative counters".into());
    }
    if let Some(a) = &task.attempt
        && a.n != task.attempt_count
    {
        return Err("open attempt number differs from attempt_count".into());
    }
    Ok(())
}
