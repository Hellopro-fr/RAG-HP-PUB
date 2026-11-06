//! Per-actor token buckets for `report` and `wait_for_updates` (§12). In-process: phase 1 runs a
//! single instance (see DECISIONS.md).

use std::collections::HashMap;
use std::sync::Mutex;
use std::time::Instant;

use uuid::Uuid;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum Bucket {
    Report,
    Wait,
}

#[derive(Default)]
pub struct RateLimiter {
    buckets: Mutex<HashMap<(Uuid, Bucket), (f64, Instant)>>,
}

impl RateLimiter {
    /// Take one token from a bucket refilled at `per_minute`, holding at most `per_minute`.
    pub fn allow(&self, actor: Uuid, bucket: Bucket, per_minute: u32) -> bool {
        self.allow_at(actor, bucket, per_minute, Instant::now())
    }

    fn allow_at(&self, actor: Uuid, bucket: Bucket, per_minute: u32, now: Instant) -> bool {
        let cap = f64::from(per_minute.max(1));
        let mut map = self.buckets.lock().unwrap_or_else(|p| p.into_inner());
        let (tokens, last) = map.entry((actor, bucket)).or_insert((cap, now));
        let refill = now.duration_since(*last).as_secs_f64() * cap / 60.0;
        *tokens = (*tokens + refill).min(cap);
        *last = now;
        if *tokens >= 1.0 {
            *tokens -= 1.0;
            true
        } else {
            false
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::Duration;

    #[test]
    fn bucket_empties_then_refills() {
        let rl = RateLimiter::default();
        let a = Uuid::now_v7();
        let t0 = Instant::now();
        for _ in 0..3 {
            assert!(rl.allow_at(a, Bucket::Report, 3, t0));
        }
        assert!(!rl.allow_at(a, Bucket::Report, 3, t0));
        assert!(
            rl.allow_at(a, Bucket::Wait, 3, t0),
            "buckets are independent"
        );
        assert!(rl.allow_at(a, Bucket::Report, 3, t0 + Duration::from_secs(20)));
    }
}
