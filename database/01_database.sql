-- MedSync database initialization, PostgreSQL 16+.
-- Create/select the database through the host tooling first. This file never
-- drops populated tables. Run 02-10 only in a new, empty application schema;
-- an existing database requires reviewed forward migrations, not a reset.
CREATE SCHEMA IF NOT EXISTS public;
