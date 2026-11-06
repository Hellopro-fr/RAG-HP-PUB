//! Minimal Prometheus counters/gauges rendered in the text exposition format (`GET /metrics`).

use std::fmt::Write;
use std::sync::atomic::{AtomicI64, AtomicU64, Ordering};

#[derive(Debug, Default)]
pub struct Metrics {
    pub claims_total: AtomicU64,
    pub lease_expiries_total: AtomicU64,
    pub commands_total: AtomicU64,
    pub command_errors_total: AtomicU64,
    pub tests_passed_total: AtomicU64,
    pub tests_failed_total: AtomicU64,
    pub reviews_approved_total: AtomicU64,
    pub reviews_rejected_total: AtomicU64,
    pub sse_clients: AtomicI64,
}

impl Metrics {
    pub fn inc(counter: &AtomicU64) {
        counter.fetch_add(1, Ordering::Relaxed);
    }

    pub fn render(&self) -> String {
        let g = |c: &AtomicU64| c.load(Ordering::Relaxed);
        let counters = [
            (
                "atb_claims_total",
                "Leases granted by claim.",
                g(&self.claims_total),
            ),
            (
                "atb_lease_expiries_total",
                "Leases expired by the sweeper.",
                g(&self.lease_expiries_total),
            ),
            (
                "atb_commands_total",
                "Commands executed.",
                g(&self.commands_total),
            ),
            (
                "atb_command_errors_total",
                "Commands rejected or failed.",
                g(&self.command_errors_total),
            ),
            (
                "atb_test_results_passed_total",
                "Passed test runs.",
                g(&self.tests_passed_total),
            ),
            (
                "atb_test_results_failed_total",
                "Failed test runs.",
                g(&self.tests_failed_total),
            ),
            (
                "atb_review_verdicts_approved_total",
                "Approved reviews.",
                g(&self.reviews_approved_total),
            ),
            (
                "atb_review_verdicts_changes_requested_total",
                "Reviews requesting changes.",
                g(&self.reviews_rejected_total),
            ),
        ];
        let mut out = String::new();
        for (name, help, v) in counters {
            let _ = writeln!(
                out,
                "# HELP {name} {help}\n# TYPE {name} counter\n{name} {v}"
            );
        }
        let _ = writeln!(
            out,
            "# HELP atb_sse_clients Open SSE connections.\n# TYPE atb_sse_clients gauge\natb_sse_clients {}",
            self.sse_clients.load(Ordering::Relaxed)
        );
        out
    }
}

/// Counts an open SSE stream for as long as it lives.
pub struct SseGuard(std::sync::Arc<Metrics>);

impl SseGuard {
    pub fn new(m: std::sync::Arc<Metrics>) -> Self {
        m.sse_clients.fetch_add(1, Ordering::Relaxed);
        Self(m)
    }
}

impl Drop for SseGuard {
    fn drop(&mut self) {
        self.0.sse_clients.fetch_sub(1, Ordering::Relaxed);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn render_exposes_counters_and_the_sse_gauge() {
        let m = std::sync::Arc::new(Metrics::default());
        Metrics::inc(&m.claims_total);
        let guard = SseGuard::new(m.clone());
        let text = m.render();
        assert!(text.contains("atb_claims_total 1"));
        assert!(text.contains("atb_sse_clients 1"));
        drop(guard);
        assert!(m.render().contains("atb_sse_clients 0"));
    }
}
