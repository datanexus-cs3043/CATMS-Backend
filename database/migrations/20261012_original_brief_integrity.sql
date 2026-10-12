-- Forward-only original-brief integrity alignment; no record backfill or deletion.
-- Review existing manager roles, doctor/visit branches and invoice lifecycle before
-- applying to a populated target. Existing mismatches must be resolved explicitly.
BEGIN;

-- Fail before replacing objects if a populated target has incompatible history.
-- No automatic repair, reassignment, deletion or seed replay is performed here.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM branch b JOIN staff s ON s.staff_id=b.manager_staff_id
               WHERE s.branch_id<>b.branch_id
                  OR LOWER(REPLACE(BTRIM(s.role), ' ', '_')) NOT IN ('branch_manager', 'manager'))
       OR EXISTS (SELECT 1 FROM appointment a JOIN doctor d USING (doctor_id)
                  JOIN staff s USING (staff_id) WHERE a.branch_id<>s.branch_id)
       OR EXISTS (SELECT 1 FROM invoice i JOIN appointment a USING (appointment_id)
                  JOIN staff s USING (staff_id) WHERE a.status<>'Completed' OR a.branch_id<>s.branch_id) THEN
        RAISE EXCEPTION 'Resolve existing manager, doctor-branch or invoice-lifecycle inconsistencies before applying this migration';
    END IF;
END;
$$;

CREATE OR REPLACE FUNCTION fn_validate_branch_manager()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    -- A new branch may be provisioned before its staff; an assigned manager must
    -- actually hold the manager role at this branch, not just have a valid FK.
    IF NEW.manager_staff_id IS NOT NULL THEN
        PERFORM staff_id FROM staff
         WHERE staff_id = NEW.manager_staff_id AND branch_id = NEW.branch_id
           AND LOWER(REPLACE(BTRIM(role), ' ', '_')) IN ('branch_manager', 'manager')
         FOR SHARE;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'Assigned manager must be a branch manager at this branch'
                USING ERRCODE = 'check_violation';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION fn_validate_staff_assignment()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    IF EXISTS (SELECT 1 FROM branch WHERE manager_staff_id = OLD.staff_id
               AND (branch_id <> NEW.branch_id
                    OR LOWER(REPLACE(BTRIM(NEW.role), ' ', '_')) NOT IN ('branch_manager', 'manager'))) THEN
        RAISE EXCEPTION 'Assign a replacement branch manager before moving or changing this staff role'
            USING ERRCODE = 'check_violation';
    END IF;
    -- Historical visits and financial attribution must not silently change branch
    -- when the linked staff record is edited. Transfers need a separate history model.
    IF NEW.branch_id IS DISTINCT FROM OLD.branch_id AND (
        EXISTS (SELECT 1 FROM appointment a JOIN doctor d USING (doctor_id)
                 WHERE d.staff_id = OLD.staff_id)
        OR EXISTS (SELECT 1 FROM invoice WHERE staff_id = OLD.staff_id)
        OR EXISTS (SELECT 1 FROM patient_payment WHERE received_by = OLD.staff_id)
    ) THEN
        RAISE EXCEPTION 'Staff with visit or financial history cannot change branch'
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION fn_prepare_invoice()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_billed NUMERIC(12, 2);
    v_appointment appointment%ROWTYPE;
BEGIN
    IF TG_OP = 'UPDATE' AND NEW.appointment_id IS DISTINCT FROM OLD.appointment_id THEN
        RAISE EXCEPTION 'An issued invoice cannot move to another appointment'
            USING ERRCODE = 'check_violation';
    END IF;
    SELECT * INTO v_appointment FROM appointment
     WHERE appointment_id = NEW.appointment_id FOR UPDATE;
    IF NOT FOUND OR v_appointment.status <> 'Completed' THEN
        RAISE EXCEPTION 'Only completed appointments can be invoiced'
            USING ERRCODE = 'check_violation';
    END IF;
    PERFORM staff_id FROM staff
     WHERE staff_id = NEW.staff_id AND branch_id = v_appointment.branch_id FOR SHARE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Invoice staff must belong to the appointment branch'
            USING ERRCODE = 'check_violation';
    END IF;
    IF TG_OP = 'INSERT' THEN
        v_billed := NEW.amount_paid + NEW.balance;
    ELSE
        v_billed := OLD.amount_paid + OLD.balance;
        IF NEW.balance IS DISTINCT FROM OLD.balance THEN
            v_billed := NEW.amount_paid + NEW.balance;
        END IF;
    END IF;

    IF NEW.amount_paid < 0 OR v_billed < NEW.amount_paid THEN
        RAISE EXCEPTION 'Invoice amount paid cannot be negative or exceed the billed amount'
            USING ERRCODE = 'check_violation';
    END IF;

    NEW.balance := v_billed - NEW.amount_paid;
    NEW.status := CASE
        WHEN NEW.balance = 0 THEN 'Paid'
        WHEN NEW.amount_paid > 0 THEN 'Partially Paid'
        ELSE 'Unpaid'
    END;
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION fn_validate_appointment()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_original appointment%ROWTYPE;
    v_doctor_branch INTEGER;
BEGIN
    -- Protect direct SQL as well as API booking. Lock the staff assignment while
    -- this slot is written; transferring a doctor with visit history is refused.
    SELECT s.branch_id INTO v_doctor_branch FROM doctor d JOIN staff s USING (staff_id)
     WHERE d.doctor_id = NEW.doctor_id FOR SHARE OF d, s;
    IF NOT FOUND OR v_doctor_branch IS DISTINCT FROM NEW.branch_id THEN
        RAISE EXCEPTION 'Doctor must belong to the appointment branch'
            USING ERRCODE = 'check_violation';
    END IF;
    IF NEW.end_time <= NEW.start_time THEN
        RAISE EXCEPTION 'Appointment end time must be later than start time'
            USING ERRCODE = 'check_violation';
    END IF;

    IF TG_OP = 'UPDATE'
       AND OLD.status IN ('Completed', 'Cancelled')
       AND NEW.status IS DISTINCT FROM OLD.status THEN
        RAISE EXCEPTION 'Completed or cancelled appointments cannot be reopened'
            USING ERRCODE = 'check_violation';
    END IF;

    IF NEW.status = 'Completed' AND NEW.treatment_id IS NULL
       AND NOT EXISTS (SELECT 1 FROM appointment_treatment WHERE appointment_id = NEW.appointment_id)
       AND NOT EXISTS (SELECT 1 FROM consultation_note WHERE appointment_id = NEW.appointment_id) THEN
        RAISE EXCEPTION 'A completed appointment requires a treatment or consultation note'
            USING ERRCODE = 'check_violation';
    END IF;

    IF NEW.original_appointment_id IS NOT NULL THEN
        SELECT * INTO v_original
          FROM appointment
         WHERE appointment_id = NEW.original_appointment_id
         FOR UPDATE;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'Original appointment % does not exist',
                NEW.original_appointment_id
                USING ERRCODE = 'foreign_key_violation';
        END IF;
        IF v_original.patient_id <> NEW.patient_id
           OR v_original.doctor_id <> NEW.doctor_id
           OR v_original.branch_id <> NEW.branch_id THEN
            RAISE EXCEPTION 'Rescheduled appointment must retain the patient, doctor, and branch'
                USING ERRCODE = 'check_violation';
        END IF;
        IF TG_OP = 'INSERT' THEN
            IF v_original.status <> 'Scheduled' THEN
                RAISE EXCEPTION 'Only a scheduled appointment can be rescheduled'
                    USING ERRCODE = 'check_violation';
            END IF;
            UPDATE appointment
               SET status = 'Cancelled'
             WHERE appointment_id = NEW.original_appointment_id;
        END IF;
    END IF;
    RETURN NEW;
END;
$$;

CREATE OR REPLACE TRIGGER trg_branch_manager_validate
BEFORE INSERT OR UPDATE OF manager_staff_id ON branch
FOR EACH ROW EXECUTE FUNCTION fn_validate_branch_manager();

CREATE OR REPLACE TRIGGER trg_staff_assignment_validate
BEFORE UPDATE OF branch_id, role ON staff
FOR EACH ROW EXECUTE FUNCTION fn_validate_staff_assignment();

CREATE OR REPLACE TRIGGER trg_invoice_prepare
BEFORE INSERT OR UPDATE OF appointment_id, staff_id, amount_paid, balance, status ON invoice
FOR EACH ROW EXECUTE FUNCTION fn_prepare_invoice();

CREATE INDEX IF NOT EXISTS idx_user_username_lower ON "user" (LOWER(username));
CREATE INDEX IF NOT EXISTS idx_user_email_lower ON "user" (LOWER(email));

-- PostgreSQL NUMERIC accepts NaN (and treats it as greater than ordinary values).
-- Nonnegative checks alone therefore do not guarantee usable monetary values.
DO $finite$
DECLARE
    rule RECORD;
BEGIN
    FOR rule IN SELECT * FROM (VALUES
        ('treatment', 'standard_price::text NOT IN (''NaN'', ''Infinity'', ''-Infinity'')'),
        ('appointment_treatment', 'unitprice::text NOT IN (''NaN'', ''Infinity'', ''-Infinity'')'),
        ('invoice', 'amount_paid::text NOT IN (''NaN'', ''Infinity'', ''-Infinity'') AND balance::text NOT IN (''NaN'', ''Infinity'', ''-Infinity'')'),
        ('invoice_item', 'unitprice::text NOT IN (''NaN'', ''Infinity'', ''-Infinity'')'),
        ('patient_payment', 'amount::text NOT IN (''NaN'', ''Infinity'', ''-Infinity'')'),
        ('doctor_payment', 'doctor_payment::text NOT IN (''NaN'', ''Infinity'', ''-Infinity'')'),
        ('insurance_coverage', 'coverage_percentage::text NOT IN (''NaN'', ''Infinity'', ''-Infinity'') AND maximum_amount::text NOT IN (''NaN'', ''Infinity'', ''-Infinity'')'),
        ('insurance_claim', 'claim_amount::text NOT IN (''NaN'', ''Infinity'', ''-Infinity'') AND approved_amount::text NOT IN (''NaN'', ''Infinity'', ''-Infinity'')')
    ) AS checks(table_name, expression)
    LOOP
        IF NOT EXISTS (SELECT 1 FROM pg_constraint
                       WHERE conrelid = to_regclass(rule.table_name)
                         AND conname = 'ck_finite_financial_values') THEN
            EXECUTE format('ALTER TABLE %I ADD CONSTRAINT ck_finite_financial_values CHECK (%s)',
                           rule.table_name, rule.expression);
        END IF;
    END LOOP;
END;
$finite$;

-- Completed treatment quantities, including visits not yet invoiced. Existing
-- columns remain in place; use the appended appointment_date for period filters.
CREATE OR REPLACE VIEW v_treatment_category_usage AS
SELECT tc.category_id,
       tc.category_name,
       t.treatment_id,
       t.treatment_name,
       i.invoice_date,
       a.branch_id,
       COALESCE(SUM(at.quantity), 0)::BIGINT AS usage_count,
       COALESCE(SUM(at.quantity * at.unitprice), 0)::NUMERIC(12, 2) AS treatment_revenue,
       a.appointment_date
FROM treatment_category tc
JOIN treatment t ON t.category_id = tc.category_id
JOIN appointment_treatment at ON at.treatment_id = t.treatment_id
JOIN appointment a ON a.appointment_id = at.appointment_id AND a.status = 'Completed'
LEFT JOIN invoice i ON i.appointment_id = a.appointment_id
GROUP BY tc.category_id, tc.category_name, t.treatment_id,
         t.treatment_name, i.invoice_date, a.branch_id, a.appointment_date;

COMMIT;

