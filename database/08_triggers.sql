-- MedSync CATMS - Database Triggers (08_triggers.sql)
-- Target: PostgreSQL 16+ (Neon Cloud / Local)

-- Database-level integrity rules. Run after 05_views.sql, 06_functions.sql,
-- and 07_procedures.sql.

CREATE EXTENSION IF NOT EXISTS btree_gist;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'ex_appointment_doctor_time'
          AND conrelid = 'appointment'::regclass
    ) THEN
        ALTER TABLE appointment
            ADD CONSTRAINT ex_appointment_doctor_time
            EXCLUDE USING gist (
                doctor_id WITH =,
                (tsrange(appointment_date + start_time,
                         appointment_date + end_time, '[)')) WITH &&
            )
            WHERE (status <> 'Cancelled');
    END IF;
END;
$$;