-- Least privilege for the runtime role (atb_app, created by deploy/postgres-init).
-- events is append-only: no UPDATE, DELETE or TRUNCATE for the app role.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'atb_app') THEN
        GRANT USAGE ON SCHEMA public TO atb_app;
        GRANT SELECT, INSERT, UPDATE, DELETE ON
            projects, actors, sessions, specs, spec_versions, tasks, task_links,
            leases, attempts, questions, idempotency_keys
        TO atb_app;
        GRANT SELECT, INSERT ON events TO atb_app;
        REVOKE UPDATE, DELETE, TRUNCATE ON events FROM atb_app;
    END IF;
END
$$;
