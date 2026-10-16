-- infra/db/init/00-init.sql
--
-- One-time Postgres bootstrap for the r01 walking-skeleton stack. Runs via
-- the official postgres image's /docker-entrypoint-initdb.d mechanism on
-- first container start only (i.e. when the postgres-data volume is empty),
-- AFTER the image's own initdb phase has already created the `monolith`
-- database and `monolith` user/password from the POSTGRES_DB/POSTGRES_USER/
-- POSTGRES_PASSWORD env vars set in compose.yaml (see .env.example) — that
-- satisfies postgresql://monolith:monolith@localhost:5432/monolith.
--
-- Scope discipline: this file intentionally does NOT create application
-- tables or seed data. Schema ownership (Alembic/SQLAlchemy migrations, the
-- monolith's bounded-context tables, deterministic seed data) belongs to the
-- monolith module itself, once it lands. This script only ensures the
-- extensions the first migration will want are present so it doesn't need
-- superuser privileges to add them later.

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
