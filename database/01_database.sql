-- Database initialization for PostgreSQL / Neon
-- Note: Neon automatically provides and connects to the target database (default: neondb).
-- For local PostgreSQL environments, create the database if not already created.

CREATE SCHEMA IF NOT EXISTS public;
CREATE DATABASE medsync;

DROP TABLE IF EXISTS doctor_payment CASCADE;
DROP TABLE IF EXISTS insurance_claim CASCADE;
DROP TABLE IF EXISTS insurance_coverage CASCADE;
DROP TABLE IF EXISTS consultation_note CASCADE;
DROP TABLE IF EXISTS invoice_item CASCADE;
DROP TABLE IF EXISTS invoice CASCADE;
DROP TABLE IF EXISTS appointment CASCADE;
DROP TABLE IF EXISTS doctor_specialty CASCADE;
DROP TABLE IF EXISTS doctor CASCADE;
DROP TABLE IF EXISTS treatment CASCADE;
DROP TABLE IF EXISTS treatment_category CASCADE;
DROP TABLE IF EXISTS insurance_policy CASCADE;
DROP TABLE IF EXISTS insurance_provider CASCADE;
DROP TABLE IF EXISTS emergency_contact CASCADE;
DROP TABLE IF EXISTS patient CASCADE;
DROP TABLE IF EXISTS specialty CASCADE;
DROP TABLE IF EXISTS staff CASCADE;
DROP TABLE IF EXISTS users_logins CASCADE;
DROP TABLE IF EXISTS branch CASCADE;
DROP TABLE IF EXISTS "user" CASCADE;