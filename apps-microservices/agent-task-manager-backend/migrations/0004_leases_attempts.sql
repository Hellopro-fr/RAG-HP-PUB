-- Leases and attempts. leases.expires_at / last_heartbeat_at are volatile timing fields.
CREATE TABLE leases (
    task_id            uuid PRIMARY KEY REFERENCES tasks (id),
    actor_id           uuid NOT NULL REFERENCES actors (id),
    kind               text NOT NULL CHECK (kind IN ('work', 'review')),
    token_hash         text NOT NULL,
    expires_at         timestamptz NOT NULL,
    paused             boolean NOT NULL DEFAULT false,
    last_heartbeat_at  timestamptz,
    created_at         timestamptz NOT NULL,
    updated_at         timestamptz NOT NULL
);
-- Sweeper scan.
CREATE INDEX leases_expiry_idx ON leases (expires_at) WHERE NOT paused;

CREATE TABLE attempts (
    id            uuid PRIMARY KEY,
    task_id       uuid NOT NULL REFERENCES tasks (id),
    n             int NOT NULL,
    actor_id      uuid NOT NULL REFERENCES actors (id),
    actor_model   text,
    started_at    timestamptz NOT NULL,
    ended_at      timestamptz,
    outcome       text CHECK (outcome IN ('released', 'expired', 'rejected', 'approved')),
    commit_sha    text,
    branch        text,
    handoff_note  text,
    trace_id      text,
    created_at    timestamptz NOT NULL,
    updated_at    timestamptz NOT NULL,
    UNIQUE (task_id, n)
);
CREATE INDEX attempts_actor_idx ON attempts (actor_id);
-- At most one open attempt per task.
CREATE UNIQUE INDEX attempts_open_idx ON attempts (task_id) WHERE ended_at IS NULL;
