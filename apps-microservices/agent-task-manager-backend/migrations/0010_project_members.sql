-- Public/private projects, members (people and teams), invitations, agent owners, disabled users.
-- Configuration, not event-sourced (like projects, actors and access_rules).

-- Projects created before this migration stay readable by everyone (public); new ones are
-- private unless the creator says otherwise.
ALTER TABLE projects
    ADD COLUMN visibility text NOT NULL DEFAULT 'public'
        CHECK (visibility IN ('public', 'private'));
ALTER TABLE projects ALTER COLUMN visibility SET DEFAULT 'private';

-- The human who connected an agent: the agent sees the projects its owner sees (capped at
-- editor). NULL = created by an admin from the CLI or before this migration: unrestricted.
ALTER TABLE actors ADD COLUMN owner_id uuid REFERENCES actors (id);
-- Access to the board disabled by an admin (the HelloPro account is untouched).
ALTER TABLE actors ADD COLUMN disabled_at timestamptz;
CREATE INDEX actors_owner_idx ON actors (owner_id);

-- subject_id: the lower-cased login (= email for HelloPro accounts) for a person, the
-- account-service group id for a team. A person can be invited before their first sign-in.
-- accepted_at NULL = pending invitation (gives no access yet); teams are accepted at once.
CREATE TABLE project_members (
    project_id    uuid NOT NULL REFERENCES projects (id) ON DELETE CASCADE,
    subject_kind  text NOT NULL CHECK (subject_kind IN ('user', 'team')),
    subject_id    text NOT NULL CHECK (length(subject_id) BETWEEN 1 AND 255),
    role          text NOT NULL CHECK (role IN ('owner', 'editor', 'viewer')),
    invited_by    uuid REFERENCES actors (id),
    accepted_at   timestamptz,
    created_at    timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (project_id, subject_kind, subject_id),
    CHECK (subject_kind = 'user' OR role <> 'owner'),
    CHECK (subject_kind = 'user' OR accepted_at IS NOT NULL),
    CHECK (subject_kind <> 'user' OR subject_id = lower(subject_id))
);
CREATE INDEX project_members_subject_idx ON project_members (subject_kind, subject_id);

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'atb_app') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON project_members TO atb_app;
    END IF;
END
$$;
