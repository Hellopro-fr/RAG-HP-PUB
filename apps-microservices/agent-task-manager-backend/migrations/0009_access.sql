-- Access settings ("Accès" page). Configuration, not event-sourced (like actors and sessions).
-- A row is an explicit setting; no row = "inherit from teams" (user) or "not set" (team).
-- subject_id: the actor id (user) or the account-service group id (team).
-- access.manage is not storable: it belongs to the Admin level only.
CREATE TABLE access_rules (
    subject_kind  text NOT NULL CHECK (subject_kind IN ('user', 'team')),
    subject_id    text NOT NULL CHECK (length(subject_id) BETWEEN 1 AND 64),
    permission    text NOT NULL CHECK (permission IN (
                      'projects.create', 'questions.answer', 'agents.manage',
                      'agents.view', 'users.view')),
    effect        text NOT NULL CHECK (effect IN ('allow', 'deny')),
    updated_by    uuid NOT NULL REFERENCES actors (id),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (subject_kind, subject_id, permission)
);

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'atb_app') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON access_rules TO atb_app;
    END IF;
END
$$;
