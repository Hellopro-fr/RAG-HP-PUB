-- Specs and their versions (projections of spec.* events).
CREATE TABLE specs (
    id                uuid PRIMARY KEY,
    project_id        uuid NOT NULL REFERENCES projects (id),
    title             text NOT NULL,
    approved_version  int,
    created_at        timestamptz NOT NULL,
    updated_at        timestamptz NOT NULL
);
CREATE INDEX specs_project_idx ON specs (project_id);

CREATE TABLE spec_versions (
    spec_id              uuid NOT NULL REFERENCES specs (id),
    version              int NOT NULL CHECK (version >= 1),
    body_md              text NOT NULL,
    acceptance_criteria  jsonb NOT NULL,
    protected_paths      text[] NOT NULL DEFAULT '{}',
    test_ref             text,
    status               text NOT NULL CHECK (status IN ('draft', 'approved', 'superseded')),
    author_id            uuid NOT NULL REFERENCES actors (id),
    approved_by          uuid REFERENCES actors (id),
    approved_at          timestamptz,
    created_at           timestamptz NOT NULL,
    updated_at           timestamptz NOT NULL,
    PRIMARY KEY (spec_id, version)
);
