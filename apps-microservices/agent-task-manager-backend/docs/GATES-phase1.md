# Gates: Agent Task Board phase 1

OWNS: apps-microservices/agent-task-manager-backend/**, apps-microservices/agent-task-manager-frontend/**, apps-microservices/mcp-gateway-service/**

Scope: phase 1 of the build spec (live board and agent loop) — every AC-1.x as an automated passing test, lint clean, compose stack up, demo working, gateway identity forwarding.

- [x] G1: every row of the section-4 transition table has a passing unit test and the proptest holds
  CHECK: cargo test -p atb-core 2>&1
  EXPECT: /test result: ok\. [1-9]\d* passed/
  CWD: apps-microservices/agent-task-manager-backend
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/home/hellopro/RAG-HP-PUB/apps-microservices/agent-task-manager-backend; path=0bcdded94535/19 entries; EXPECT=matched; output-sha256=3b055d61c347ec56e4f4425c1b180d8103dd014da4cd342d7d15fb595de730c0; output-bytes=3761

- [x] G2: AC-1.1 twenty concurrent claimers on five ready tasks get exactly five leases
  CHECK: bash scripts/test-pg.sh --test ac_1_1_concurrent_claim
  EXPECT: /test result: ok\. [1-9]\d* passed/
  CWD: apps-microservices/agent-task-manager-backend
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/home/hellopro/RAG-HP-PUB/apps-microservices/agent-task-manager-backend; path=0bcdded94535/19 entries; EXPECT=matched; output-sha256=61cff873c62e0e54bfceeaa517885f6626e250a13f106d8b7563f6ba0d1abb64; output-bytes=500

- [x] G3: AC-1.2 an expired lease returns the task to ready within 10 s with lease.expired and a handoff note
  CHECK: bash scripts/test-pg.sh --test ac_1_2_lease_expiry
  EXPECT: /test result: ok\. [1-9]\d* passed/
  CWD: apps-microservices/agent-task-manager-backend
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/home/hellopro/RAG-HP-PUB/apps-microservices/agent-task-manager-backend; path=0bcdded94535/19 entries; EXPECT=matched; output-sha256=7bd7d68dbca88a84a9d6fe4406fbe31265cd126b15ba75fc0bc02c6f2c00ce12; output-bytes=495

- [x] G4: AC-1.3 expired or foreign lease tokens are rejected with stale_lease
  CHECK: bash scripts/test-pg.sh --test ac_1_3_stale_lease
  EXPECT: /test result: ok\. [1-9]\d* passed/
  CWD: apps-microservices/agent-task-manager-backend
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/home/hellopro/RAG-HP-PUB/apps-microservices/agent-task-manager-backend; path=0bcdded94535/19 entries; EXPECT=matched; output-sha256=275dda5273b93961e2aa7507a97c4ca50e0719e9527f9e64f1879d7f7f3ab90a; output-bytes=491

- [x] G5: AC-1.4 blocking ask releases the lease; answer returns the task to ready with asker preference
  CHECK: bash scripts/test-pg.sh --test ac_1_4_blocking_question
  EXPECT: /test result: ok\. [1-9]\d* passed/
  CWD: apps-microservices/agent-task-manager-backend
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/home/hellopro/RAG-HP-PUB/apps-microservices/agent-task-manager-backend; path=0bcdded94535/19 entries; EXPECT=matched; output-sha256=25c646099020277ac7f877cc85da63cd0707a77e346c2063f74b58a8d6084611; output-bytes=507

- [x] G6: AC-1.5 a blocks link that would create a cycle is rejected
  CHECK: bash scripts/test-pg.sh --test ac_1_5_cycle
  EXPECT: /test result: ok\. [1-9]\d* passed/
  CWD: apps-microservices/agent-task-manager-backend
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/home/hellopro/RAG-HP-PUB/apps-microservices/agent-task-manager-backend; path=0bcdded94535/19 entries; EXPECT=matched; output-sha256=bad1014ead4e61c8d4143a1fc56b3bdfacd8ad24b82158147ada8101a406ed27; output-bytes=453

- [x] G7: AC-1.6 a reused idempotency key returns the first response and applies once
  CHECK: bash scripts/test-pg.sh --test ac_1_6_idempotency
  EXPECT: /test result: ok\. [1-9]\d* passed/
  CWD: apps-microservices/agent-task-manager-backend
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/home/hellopro/RAG-HP-PUB/apps-microservices/agent-task-manager-backend; path=0bcdded94535/19 entries; EXPECT=matched; output-sha256=7b46e667fbc396994e43f7126f8c95650a00d016bd32abc975eafcddec277555; output-bytes=517

- [x] G8: AC-1.7 (server half) SSE reconnect with Last-Event-ID replays in order without duplicates
  CHECK: bash scripts/test-pg.sh --test ac_1_7_sse_replay
  EXPECT: /test result: ok\. [1-9]\d* passed/
  CWD: apps-microservices/agent-task-manager-backend
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/home/hellopro/RAG-HP-PUB/apps-microservices/agent-task-manager-backend; path=0bcdded94535/19 entries; EXPECT=matched; output-sha256=42bdcac17852911895c30e78a5b2e8a18d27192ea9a58dd8be790c2deb001d82; output-bytes=547

- [x] G9: AC-1.7 (browser half) a committed state change shows on two open boards within 1 s
  CHECK: npx playwright test e2e/board-live.spec.ts --reporter=line 2>&1
  EXPECT: /[1-9]\d* passed/
  CWD: apps-microservices/agent-task-manager-frontend
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/home/hellopro/RAG-HP-PUB/apps-microservices/agent-task-manager-frontend; path=0bcdded94535/19 entries; EXPECT=matched; output-sha256=e9964cd3ee204fdeb559647bb06532610ac194e167466017289e622e7f1e8390; output-bytes=270

- [x] G10: AC-1.8 projections rebuilt from the event log equal the live tables (volatile fields excepted)
  CHECK: bash scripts/test-pg.sh --test ac_1_8_rebuild
  EXPECT: /test result: ok\. [1-9]\d* passed/
  CWD: apps-microservices/agent-task-manager-backend
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/home/hellopro/RAG-HP-PUB/apps-microservices/agent-task-manager-backend; path=0bcdded94535/19 entries; EXPECT=matched; output-sha256=b44da7833a63306cc0dd907ea136914499f4200da1cfc466cc9399d67d6c916d; output-bytes=478

- [x] G11: AC-1.9 an MCP client completes list_ready, claim, report, ask, answer, claim, release over /mcp
  CHECK: bash scripts/test-pg.sh --test ac_1_9_mcp_loop
  EXPECT: /test result: ok\. [1-9]\d* passed/
  CWD: apps-microservices/agent-task-manager-backend
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/home/hellopro/RAG-HP-PUB/apps-microservices/agent-task-manager-backend; path=0bcdded94535/19 entries; EXPECT=matched; output-sha256=2d790bbaa2dc54b05823ae9e0b57700367c0ea95500072275526ffd499105d1a; output-bytes=510

- [x] G12: the app DB role cannot UPDATE or DELETE events while INSERT works
  CHECK: bash scripts/test-pg.sh --test db_role_events_append_only
  EXPECT: /test result: ok\. [1-9]\d* passed/
  CWD: apps-microservices/agent-task-manager-backend
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/home/hellopro/RAG-HP-PUB/apps-microservices/agent-task-manager-backend; path=0bcdded94535/19 entries; EXPECT=matched; output-sha256=e10c4e15e7cbd7faa29b03d992c150ad55800c9817c63f0a99a31e3b4b454ac3; output-bytes=487

- [x] G13: backend is fmt and clippy clean with warnings denied
  CHECK: cargo fmt --all --check && cargo clippy --workspace --all-targets -- -D warnings && echo ATB_LINT_CLEAN
  EXPECT: ATB_LINT_CLEAN
  CWD: apps-microservices/agent-task-manager-backend
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/home/hellopro/RAG-HP-PUB/apps-microservices/agent-task-manager-backend; path=0bcdded94535/19 entries; EXPECT=matched; output-sha256=3005670a41cb40ac1db5215c45454e0203997be67d11b49bb913f0c1d0b1fed1; output-bytes=88

- [x] G14: frontend typechecks, lints and its realtime reducer tests pass
  CHECK: npm run typecheck && npm run lint && npx vitest run && echo ATB_WEB_CHECKS_OK
  EXPECT: ATB_WEB_CHECKS_OK
  CWD: apps-microservices/agent-task-manager-frontend
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/home/hellopro/RAG-HP-PUB/apps-microservices/agent-task-manager-frontend; path=0bcdded94535/19 entries; EXPECT=matched; output-sha256=fbf1cfca463d30e2c7db3775f15952ddf169d2bf4102b306614bf3cb1e62702f; output-bytes=368

- [x] G15: board, task detail, questions inbox and agents pages render live data end to end
  CHECK: npx playwright test e2e/pages.spec.ts --reporter=line 2>&1
  EXPECT: /[1-9]\d* passed/
  CWD: apps-microservices/agent-task-manager-frontend
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/home/hellopro/RAG-HP-PUB/apps-microservices/agent-task-manager-frontend; path=0bcdded94535/19 entries; EXPECT=matched; output-sha256=69f0b3be33284eb9893ba6d1c89f13dfeb35453b87095f9e649b1e419e6d4518; output-bytes=149

- [x] G16: docker compose up starts postgres, server, web and ingress healthy
  CHECK: bash scripts/smoke.sh
  EXPECT: ATB_SMOKE_OK
  CWD: apps-microservices/agent-task-manager-backend
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/home/hellopro/RAG-HP-PUB/apps-microservices/agent-task-manager-backend; path=0bcdded94535/19 entries; EXPECT=matched; output-sha256=3299d187a087e379b36c6a8d317463badf1b136307fe424466c3b6162c286932; output-bytes=1286

- [x] G17: scripts/demo runs two agents through work, ask, answer and the event log shows it
  CHECK: python3 scripts/demo --assert
  EXPECT: ATB_DEMO_OK
  CWD: apps-microservices/agent-task-manager-backend
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/home/hellopro/RAG-HP-PUB/apps-microservices/agent-task-manager-backend; path=0bcdded94535/19 entries; EXPECT=matched; output-sha256=484b0f6381698385a6a44413a04ea27bae59fa6b0a8ce7154c2692a550ab3958; output-bytes=1361

- [x] G18: committed openapi.json and frontend schema.d.ts match the server
  CHECK: bash scripts/check-openapi-drift.sh
  EXPECT: ATB_OPENAPI_IN_SYNC
  CWD: apps-microservices/agent-task-manager-backend
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/home/hellopro/RAG-HP-PUB/apps-microservices/agent-task-manager-backend; path=0bcdded94535/19 entries; EXPECT=matched; output-sha256=08b78442aed9fbb34367146fe5b21d4fdbd189c8ce6a878e9de0c759c407ce67; output-bytes=20

- [x] G19: gateway injects agent identity plus shared secret only for opted-in backends
  CHECK: PATH=/usr/local/go/bin:$PATH GOTOOLCHAIN=auto go test ./... -run AgentIdentity -count=1 -v 2>&1
  EXPECT: /--- PASS: Test\w*AgentIdentity/
  CWD: apps-microservices/mcp-gateway-service
  EVIDENCE: exit=0; shell=/bin/sh; cwd=/home/hellopro/RAG-HP-PUB/apps-microservices/mcp-gateway-service; path=0bcdded94535/19 entries; EXPECT=matched; output-sha256=80a0f9f7d97fed567cc1270a1a595baf0c1d03034359c6be6332ecf16b89e604; output-bytes=3278

- [x] G20: README of both services explains how to run, test and demo; DECISIONS.md lists every deviation; per-service CLAUDE.md written
  EVIDENCE: manual review 2026-11-05 — backend README.md (84 lines: run, MCP, test, layout, env), frontend README.md (46), both CLAUDE.md (39/27), DECISIONS.md with 7 DEVIATION entries + gateway CLAUDE.md updated
