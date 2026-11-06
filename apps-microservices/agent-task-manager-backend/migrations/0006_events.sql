-- Append-only event log. Per-project seq taken from projects.event_seq (gapless, commit-ordered).
CREATE TABLE events (
    project_id  uuid NOT NULL REFERENCES projects (id),
    seq         bigint NOT NULL,
    task_id     uuid,
    type        text NOT NULL,
    actor_id    uuid NOT NULL REFERENCES actors (id),
    payload     jsonb NOT NULL,
    trace_id    text,
    created_at  timestamptz NOT NULL,
    PRIMARY KEY (project_id, seq)
);
CREATE INDEX events_task_idx ON events (task_id, seq);
