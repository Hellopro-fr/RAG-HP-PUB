CREATE TABLE questions (
    id           uuid PRIMARY KEY,
    task_id      uuid NOT NULL REFERENCES tasks (id),
    asked_by     uuid NOT NULL REFERENCES actors (id),
    body         text NOT NULL,
    options      jsonb,
    blocking     boolean NOT NULL,
    status       text NOT NULL CHECK (status IN ('open', 'answered', 'withdrawn')),
    answered_by  uuid REFERENCES actors (id),
    answer       text,
    answered_at  timestamptz,
    created_at   timestamptz NOT NULL,
    updated_at   timestamptz NOT NULL
);
CREATE INDEX questions_open_idx ON questions (status, blocking DESC, created_at);
CREATE INDEX questions_task_idx ON questions (task_id);
CREATE INDEX questions_asker_idx ON questions (asked_by);
