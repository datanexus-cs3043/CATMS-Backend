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

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'ck_invoice_nonnegative_amounts'
          AND conrelid = 'invoice'::regclass
    ) THEN
        ALTER TABLE invoice
            ADD CONSTRAINT ck_invoice_nonnegative_amounts
            CHECK (amount_paid >= 0 AND balance >= 0);
    END IF;
END;
$$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
         WHERE conname = 'ck_invoice_item_amounts'
           AND conrelid = 'invoice_item'::regclass
    ) THEN
        ALTER TABLE invoice_item
            ADD CONSTRAINT ck_invoice_item_amounts
            CHECK (quantity > 0 AND unitprice >= 0);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
         WHERE conname = 'ck_treatment_nonnegative_price'
           AND conrelid = 'treatment'::regclass
    ) THEN
        ALTER TABLE treatment
            ADD CONSTRAINT ck_treatment_nonnegative_price
            CHECK (standard_price >= 0);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
         WHERE conname = 'ck_insurance_coverage_limits'
           AND conrelid = 'insurance_coverage'::regclass
    ) THEN
        ALTER TABLE insurance_coverage
            ADD CONSTRAINT ck_insurance_coverage_limits
            CHECK (coverage_percentage BETWEEN 0 AND 100 AND maximum_amount >= 0);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
         WHERE conname = 'ck_insurance_claim_amounts'
           AND conrelid = 'insurance_claim'::regclass
    ) THEN
        ALTER TABLE insurance_claim
            ADD CONSTRAINT ck_insurance_claim_amounts
            CHECK (claim_amount >= 0 AND approved_amount >= 0
                   AND approved_amount <= claim_amount);
    END IF;
END;
$$;