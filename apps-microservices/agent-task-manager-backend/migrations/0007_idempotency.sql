-- First successful response per (actor, key); purged after 24 h by the sweeper.
CREATE TABLE idempotency_keys (
    actor_id    uuid NOT NULL REFERENCES actors (id),
    key         text NOT NULL CHECK (length(key) BETWEEN 1 AND 200),
    response    jsonb NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (actor_id, key)
);
CREATE INDEX idempotency_created_idx ON idempotency_keys (created_at);
