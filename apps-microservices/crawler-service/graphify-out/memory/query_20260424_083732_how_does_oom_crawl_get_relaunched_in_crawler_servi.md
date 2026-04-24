---
type: "query"
date: "2026-04-24T08:37:32.948011+00:00"
question: "How does OOM crawl get relaunched in crawler-service"
contributor: "graphify"
source_nodes: ["_relaunch_oom_crawl", "_monitor_process", "start_crawl", "_send_failure_webhook"]
---

# Q: How does OOM crawl get relaunched in crawler-service

## Answer

Full flow (all EXTRACTED from AST). Entry: _monitor_process (crawler_manager.py:L724) detects OOM condition and calls _relaunch_oom_crawl (L330). _relaunch_oom_crawl calls _publish_update (L114) then start_crawl (L129) which restarts crawl fresh, then _monitor_process (L724) again for recursive monitoring. Failure paths emit webhook via _get_or_create_failure_request_id (L450) + _send_failure_webhook (L629). Invariants from test docstrings: (Fix 3/TestRelaunchAbort:L113) _relaunch_oom_crawl aborts if status != restarting_oom; (Fix 4/TestMonitorSkipOom:L137) _monitor_process skips OOM branch if status already failed; (Fix 5/TestForceFinishIdempotent:L171) force_finish_crawl does not double-decrement. Noise: 1 INFERRED edge _relaunch_oom_crawl -> str (type hint misread).

## Source Nodes

- _relaunch_oom_crawl
- _monitor_process
- start_crawl
- _send_failure_webhook