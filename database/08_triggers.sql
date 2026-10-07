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

CREATE OR REPLACE TRIGGER trg_appointment_validate
BEFORE INSERT OR UPDATE OF
    patient_id, doctor_id, branch_id, appointment_date,
    start_time, end_time, status, original_appointment_id
ON appointment
FOR EACH ROW EXECUTE FUNCTION fn_validate_appointment();

CREATE OR REPLACE TRIGGER trg_appointment_treatment_sync
AFTER INSERT OR UPDATE OF treatment_id ON appointment
FOR EACH ROW EXECUTE FUNCTION fn_sync_appointment_treatment();

CREATE OR REPLACE TRIGGER trg_invoice_prepare
BEFORE INSERT OR UPDATE OF amount_paid, balance, status ON invoice
FOR EACH ROW EXECUTE FUNCTION fn_prepare_invoice();

CREATE OR REPLACE TRIGGER trg_invoice_seed_payment_ledger
AFTER INSERT OR UPDATE OF amount_paid ON invoice
FOR EACH ROW EXECUTE FUNCTION fn_sync_invoice_payment_ledger();

CREATE OR REPLACE TRIGGER trg_invoice_item_lock
BEFORE INSERT OR UPDATE OR DELETE ON invoice_item
FOR EACH ROW EXECUTE FUNCTION fn_lock_invoice_for_financial_change();

CREATE OR REPLACE TRIGGER trg_invoice_item_recalculate
AFTER INSERT OR UPDATE OR DELETE ON invoice_item
FOR EACH ROW EXECUTE FUNCTION fn_recalculate_invoice_item();

CREATE OR REPLACE TRIGGER trg_patient_payment_lock
BEFORE INSERT OR UPDATE OR DELETE ON patient_payment
FOR EACH ROW EXECUTE FUNCTION fn_lock_invoice_for_financial_change();

CREATE OR REPLACE TRIGGER trg_patient_payment_sync
AFTER INSERT OR UPDATE OR DELETE ON patient_payment
FOR EACH ROW EXECUTE FUNCTION fn_sync_patient_payment();

CREATE OR REPLACE TRIGGER trg_invoice_complete_appointment
AFTER INSERT ON invoice
FOR EACH ROW EXECUTE FUNCTION fn_mark_appointment_completed();

CREATE OR REPLACE TRIGGER trg_insurance_claim_validate
BEFORE INSERT OR UPDATE OF invoice_id, policy_id, claim_amount, approved_amount
ON insurance_claim
FOR EACH ROW EXECUTE FUNCTION fn_validate_insurance_claim();

CREATE OR REPLACE TRIGGER trg_doctor_payment_validate
BEFORE INSERT OR UPDATE OF doctor_id, appointment_id, invoice_item_id
ON doctor_payment
FOR EACH ROW EXECUTE FUNCTION fn_validate_doctor_payment();