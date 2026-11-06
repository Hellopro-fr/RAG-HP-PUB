-- Tasks and links (projections of task.* events).
CREATE TABLE tasks (
    id                  uuid PRIMARY KEY,
    project_id          uuid NOT NULL REFERENCES projects (id),
    parent_id           uuid REFERENCES tasks (id),
    title               text NOT NULL,
    spec_id             uuid NOT NULL REFERENCES specs (id),
    spec_version        int NOT NULL,
    state               text NOT NULL CHECK (state IN ('draft', 'ready', 'working', 'input_required',
                            'testing', 'in_review', 'done', 'failed', 'cancelled')),
    priority            int NOT NULL DEFAULT 0,
    version             int NOT NULL DEFAULT 1,
    spec_outdated       boolean NOT NULL DEFAULT false,
    preferred_actor_id  uuid REFERENCES actors (id),
    preferred_until     timestamptz,
    attempt_count       int NOT NULL DEFAULT 0,
    rejection_count     int NOT NULL DEFAULT 0,
    created_by          uuid NOT NULL REFERENCES actors (id),
    created_at          timestamptz NOT NULL,
    updated_at          timestamptz NOT NULL
);
-- Claim query: ready tasks of a project by priority then age.
CREATE INDEX tasks_claim_idx ON tasks (project_id, state, priority DESC, created_at);
CREATE INDEX tasks_spec_idx ON tasks (spec_id);

CREATE TABLE task_links (
    from_id     uuid NOT NULL REFERENCES tasks (id),
    to_id       uuid NOT NULL REFERENCES tasks (id),
    kind        text NOT NULL CHECK (kind IN ('blocks', 'discovered_from', 'related')),
    created_at  timestamptz NOT NULL,
    PRIMARY KEY (from_id, to_id, kind),
    CHECK (from_id <> to_id)
);
CREATE INDEX task_links_to_idx ON task_links (to_id, kind);
