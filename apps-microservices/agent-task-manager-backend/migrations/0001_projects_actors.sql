-- Projects, actors and human sessions. Not event-sourced (configuration, not projections).
CREATE TABLE projects (
    id          uuid PRIMARY KEY,
    name        text NOT NULL CHECK (length(trim(name)) BETWEEN 1 AND 200),
    workflow    jsonb NOT NULL,
    event_seq   bigint NOT NULL DEFAULT 0,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE actors (
    id               uuid PRIMARY KEY,
    kind             text NOT NULL CHECK (kind IN ('agent', 'human', 'verifier', 'system')),
    name             text NOT NULL CHECK (length(trim(name)) BETWEEN 1 AND 200),
    model            text,
    roles            text[] NOT NULL DEFAULT '{}'
                     CHECK (roles <@ ARRAY['admin', 'planner', 'implementer', 'reviewer']::text[]),
    token_hash       text UNIQUE,
    password_hash    text,
    login            text UNIQUE,
    gateway_subject  text UNIQUE,
    last_seen_at     timestamptz,
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now()
);

-- The system actor (sweeper, spec fan-out, failure questions).
INSERT INTO actors (id, kind, name, roles)
VALUES ('00000000-0000-7000-8000-000000000001', 'system', 'system', '{}');

CREATE TABLE sessions (
    token_hash  text PRIMARY KEY,
    actor_id    uuid NOT NULL REFERENCES actors (id),
    expires_at  timestamptz NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX sessions_actor_idx ON sessions (actor_id);
