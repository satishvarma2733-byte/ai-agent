-- Runs once when the dev database volume is first created.
-- The app connects as a regular role so Postgres row-level security applies (superusers bypass it).
CREATE ROLE avn_app LOGIN PASSWORD 'avn_app_password';
ALTER DATABASE avnagent OWNER TO avn_app;
-- pgvector is not a trusted extension, so it must be enabled by a superuser (once per database).
\connect avnagent
CREATE EXTENSION IF NOT EXISTS vector;
