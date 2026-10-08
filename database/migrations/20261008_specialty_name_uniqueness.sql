-- Existing databases only: review the target and duplicate names first.
-- Fresh databases receive this index from 04_indexes.sql instead.
-- Fails without changing records if duplicates or this index already exist.
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '30s';

CREATE UNIQUE INDEX uq_specialty_name_normalized
    ON specialty (LOWER(BTRIM(specialty_name)));

COMMIT;
