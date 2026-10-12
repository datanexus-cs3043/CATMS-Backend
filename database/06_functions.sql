-- Business rules and derived totals for the existing CATMS table contract.

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

CREATE OR REPLACE FUNCTION fn_recalculate_invoice(
    p_invoice_id INTEGER,
    p_use_item_total BOOLEAN DEFAULT FALSE,
    p_use_payment_ledger BOOLEAN DEFAULT FALSE
)
RETURNS VOID
LANGUAGE plpgsql
AS $$
DECLARE
    v_invoice invoice%ROWTYPE;
    v_billed NUMERIC(12, 2);
    v_paid NUMERIC(12, 2);
    v_item_count BIGINT;
    v_payment_count BIGINT;
BEGIN
    SELECT * INTO v_invoice
    FROM invoice
    WHERE invoice_id = p_invoice_id
    FOR UPDATE;
    IF NOT FOUND THEN
        RETURN;
    END IF;

    SELECT COUNT(*), COALESCE(SUM(quantity * unitprice), 0)
      INTO v_item_count, v_billed
      FROM invoice_item
     WHERE invoice_id = p_invoice_id;
    IF v_item_count = 0 AND NOT p_use_item_total THEN
        v_billed := v_invoice.amount_paid + v_invoice.balance;
    END IF;

    SELECT COUNT(*), COALESCE(SUM(amount), 0)
      INTO v_payment_count, v_paid
      FROM patient_payment
     WHERE invoice_id = p_invoice_id;
    IF v_payment_count = 0 AND NOT p_use_payment_ledger THEN
        v_paid := v_invoice.amount_paid;
    END IF;

    IF v_billed < 0 OR v_paid < 0 OR v_paid > v_billed THEN
        RAISE EXCEPTION 'Invoice % totals are invalid: billed %, paid %',
            p_invoice_id, v_billed, v_paid
            USING ERRCODE = 'check_violation';
    END IF;

    UPDATE invoice
       SET amount_paid = v_paid,
           balance = v_billed - v_paid,
           status = CASE
               WHEN v_billed = v_paid THEN 'Paid'
               WHEN v_paid > 0 THEN 'Partially Paid'
               ELSE 'Unpaid'
           END
     WHERE invoice_id = p_invoice_id;
END;
$$;


CREATE OR REPLACE FUNCTION fn_recalculate_invoice_item()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        PERFORM fn_recalculate_invoice(OLD.invoice_id, TRUE);
    ELSIF TG_OP = 'UPDATE' AND OLD.invoice_id IS DISTINCT FROM NEW.invoice_id THEN
        PERFORM fn_recalculate_invoice(OLD.invoice_id, TRUE);
        PERFORM fn_recalculate_invoice(NEW.invoice_id, TRUE);
    ELSE
        PERFORM fn_recalculate_invoice(NEW.invoice_id, TRUE);
    END IF;
    RETURN NULL;
END;
$$;

CREATE OR REPLACE FUNCTION fn_lock_invoice_for_financial_change()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_invoice_ids INTEGER[];
BEGIN
    IF TG_OP = 'INSERT' THEN
        v_invoice_ids := ARRAY[NEW.invoice_id];
    ELSIF TG_OP = 'DELETE' THEN
        v_invoice_ids := ARRAY[OLD.invoice_id];
    ELSE
        v_invoice_ids := ARRAY[OLD.invoice_id, NEW.invoice_id];
    END IF;

    PERFORM invoice_id
      FROM invoice
     WHERE invoice_id = ANY(v_invoice_ids)
     ORDER BY invoice_id
     FOR UPDATE;

    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
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

CREATE OR REPLACE FUNCTION fn_sync_invoice_payment_ledger()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_ledger_paid NUMERIC(12, 2);
    v_delta NUMERIC(12, 2);
BEGIN
    -- Internal invoice updates made by the payment trigger already reflect the ledger.
    IF pg_trigger_depth() > 1 THEN
        RETURN NULL;
    END IF;

    IF TG_OP = 'INSERT' THEN
        IF NEW.amount_paid > 0 THEN
            INSERT INTO patient_payment
                (invoice_id, payment_date, amount, payment_method, payment_type)
            VALUES
                (NEW.invoice_id, NEW.invoice_date, NEW.amount_paid, 'Opening balance', 'Payment');
        END IF;
        RETURN NULL;
    END IF;

    SELECT COALESCE(SUM(amount), 0)
      INTO v_ledger_paid
      FROM patient_payment
     WHERE invoice_id = NEW.invoice_id;
    v_delta := NEW.amount_paid - v_ledger_paid;

    IF v_delta <> 0 THEN
        INSERT INTO patient_payment
            (invoice_id, payment_date, amount, payment_method, payment_type)
        VALUES
            (NEW.invoice_id, NEW.invoice_date, v_delta, 'Invoice adjustment', 'Adjustment');
    END IF;
    RETURN NULL;
END;
$$;

CREATE OR REPLACE FUNCTION fn_sync_patient_payment()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        PERFORM fn_recalculate_invoice(OLD.invoice_id, FALSE, TRUE);
    ELSIF TG_OP = 'UPDATE' AND OLD.invoice_id IS DISTINCT FROM NEW.invoice_id THEN
        PERFORM fn_recalculate_invoice(OLD.invoice_id, FALSE, TRUE);
        PERFORM fn_recalculate_invoice(NEW.invoice_id, FALSE, TRUE);
    ELSE
        PERFORM fn_recalculate_invoice(NEW.invoice_id, FALSE, TRUE);
    END IF;
    RETURN NULL;
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

CREATE OR REPLACE FUNCTION fn_sync_appointment_treatment()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_unitprice NUMERIC(10, 2);
BEGIN
    IF TG_OP = 'UPDATE'
       AND OLD.treatment_id IS DISTINCT FROM NEW.treatment_id
       AND OLD.treatment_id IS NOT NULL THEN
        DELETE FROM appointment_treatment
         WHERE appointment_id = NEW.appointment_id
           AND treatment_id = OLD.treatment_id
           AND is_primary;
    END IF;

    IF NEW.treatment_id IS NOT NULL THEN
        SELECT standard_price INTO v_unitprice
          FROM treatment
         WHERE treatment_id = NEW.treatment_id;
        INSERT INTO appointment_treatment
            (appointment_id, treatment_id, unitprice, is_primary)
        VALUES
            (NEW.appointment_id, NEW.treatment_id, v_unitprice, TRUE)
        ON CONFLICT (appointment_id, treatment_id)
        DO UPDATE SET is_primary = TRUE;
    END IF;
    RETURN NULL;
END;
$$;

CREATE OR REPLACE FUNCTION fn_mark_appointment_completed()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    UPDATE appointment
       SET status = 'Completed'
     WHERE appointment_id = NEW.appointment_id
       AND status = 'Scheduled';
    RETURN NULL;
END;
$$;


CREATE OR REPLACE FUNCTION fn_validate_insurance_claim()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_patient_id INTEGER;
    v_invoice_date DATE;
    v_policy insurance_policy%ROWTYPE;
    v_invoice_total NUMERIC;
    v_eligible NUMERIC;
    v_reserved NUMERIC;
    v_policy_reserved NUMERIC;
    v_requested NUMERIC;
BEGIN
    -- A blocking row lock cannot refresh a Repeatable Read transaction snapshot.
    -- Refuse unsupported isolation rather than validate stale reservations.
    IF current_setting('transaction_isolation') <> 'read committed' THEN
        RAISE EXCEPTION 'Insurance claim writes require Read Committed isolation'
            USING ERRCODE = 'feature_not_supported';
    END IF;

    IF TG_OP = 'UPDATE' THEN
        IF NEW.invoice_id IS DISTINCT FROM OLD.invoice_id
           OR NEW.policy_id IS DISTINCT FROM OLD.policy_id THEN
            RAISE EXCEPTION 'A filed claim cannot move to another invoice or policy'
                USING ERRCODE = 'check_violation';
        END IF;
    END IF;

    -- Serialize reservations and item/receipt changes on the invoice first.
    SELECT a.patient_id, i.invoice_date
      INTO v_patient_id, v_invoice_date
      FROM invoice i
      JOIN appointment a ON a.appointment_id = i.appointment_id
     WHERE i.invoice_id = NEW.invoice_id
     FOR UPDATE OF i;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Claim invoice does not exist'
            USING ERRCODE = 'foreign_key_violation';
    END IF;

    SELECT * INTO v_policy
      FROM insurance_policy
     WHERE policy_id = NEW.policy_id
     FOR SHARE;
    IF NOT FOUND OR v_policy.patient_id IS DISTINCT FROM v_patient_id THEN
        RAISE EXCEPTION 'Claim policy must belong to the patient on the invoice'
            USING ERRCODE = 'check_violation';
    END IF;

    IF NEW.status IS NULL OR NEW.status NOT IN ('Pending', 'Approved', 'Rejected')
       OR NEW.claim_amount IS NULL OR NEW.approved_amount IS NULL
       OR NEW.claim_amount::TEXT IN ('NaN', 'Infinity', '-Infinity')
       OR NEW.approved_amount::TEXT IN ('NaN', 'Infinity', '-Infinity')
       OR NEW.claim_amount < 0 OR NEW.approved_amount < 0
       OR NEW.approved_amount > NEW.claim_amount
       OR (NEW.status <> 'Approved' AND NEW.approved_amount <> 0) THEN
        RAISE EXCEPTION 'Insurance claim amounts or status are invalid'
            USING ERRCODE = 'check_violation';
    END IF;
    IF TG_OP = 'INSERT' THEN
        IF NEW.claim_amount <= 0 THEN
            RAISE EXCEPTION 'A new claim request must be positive'
                USING ERRCODE = 'check_violation';
        END IF;
    ELSIF NEW.claim_amount IS DISTINCT FROM OLD.claim_amount AND NEW.claim_amount <= 0 THEN
        RAISE EXCEPTION 'An explicitly changed claim request must be positive'
            USING ERRCODE = 'check_violation';
    END IF;

    -- Rejection releases a reservation, not money. A legacy excessive request,
    -- expired/inactive policy or subsequently edited coverage must not trap it.
    -- Preserve the recorded request; ownership and approved_amount = 0 still apply.
    IF NEW.status = 'Rejected' THEN
        RETURN NEW;
    END IF;

    IF v_policy.status <> 'Active'
       OR v_invoice_date < v_policy.start_date
       OR v_invoice_date > v_policy.end_date THEN
        RAISE EXCEPTION 'Insurance policy is not active on the invoice date'
            USING ERRCODE = 'check_violation';
    END IF;

    SELECT COALESCE(SUM(ii.quantity * ii.unitprice), i.amount_paid + i.balance)
      INTO v_invoice_total
      FROM invoice i
      LEFT JOIN invoice_item ii ON ii.invoice_id = i.invoice_id
     WHERE i.invoice_id = NEW.invoice_id
     GROUP BY i.invoice_id, i.amount_paid, i.balance;
    IF NEW.claim_amount > v_invoice_total THEN
        RAISE EXCEPTION 'Insurance claim request exceeds the billed invoice amount'
            USING ERRCODE = 'check_violation';
    END IF;
    IF EXISTS (
        SELECT 1 FROM invoice_item
         WHERE invoice_id = NEW.invoice_id
           AND (quantity IS NULL OR quantity <= 0 OR unitprice IS NULL
                OR unitprice < 0 OR unitprice::TEXT IN ('NaN', 'Infinity', '-Infinity'))
    ) THEN
        RAISE EXCEPTION 'Invalid invoice items prevent coverage calculation'
            USING ERRCODE = 'check_violation';
    END IF;

    PERFORM coverage_id FROM insurance_coverage
     WHERE policy_id = NEW.policy_id ORDER BY coverage_id FOR SHARE;
    IF EXISTS (
        SELECT treatment_id FROM insurance_coverage
         WHERE policy_id = NEW.policy_id
         GROUP BY treatment_id HAVING COUNT(*) > 1
    ) THEN
        RAISE EXCEPTION 'Duplicate treatment coverage rules must be resolved'
            USING ERRCODE = 'check_violation';
    END IF;

    IF EXISTS (
        SELECT 1 FROM insurance_coverage c
         WHERE c.policy_id = NEW.policy_id
           AND EXISTS (SELECT 1 FROM invoice_item ii
                        WHERE ii.invoice_id = NEW.invoice_id AND ii.treatment_id = c.treatment_id)
           AND (c.coverage_percentage IS NULL OR c.maximum_amount IS NULL
                OR c.coverage_percentage::TEXT IN ('NaN', 'Infinity', '-Infinity')
                OR c.maximum_amount::TEXT IN ('NaN', 'Infinity', '-Infinity')
                OR c.coverage_percentage NOT BETWEEN 0 AND 100 OR c.maximum_amount < 0)
    ) THEN
        RAISE EXCEPTION 'Invalid treatment coverage rules must be resolved'
            USING ERRCODE = 'check_violation';
    END IF;

    -- Group repeated frozen-price lines BEFORE applying each treatment's cap.
    WITH billed_treatments AS (
        SELECT treatment_id, SUM(quantity * unitprice) AS billed_amount
          FROM invoice_item WHERE invoice_id = NEW.invoice_id GROUP BY treatment_id
    )
    SELECT COALESCE(SUM(FLOOR(LEAST(b.billed_amount * c.coverage_percentage / 100,
                                  c.maximum_amount) * 100) / 100), 0)
      INTO v_eligible
      FROM billed_treatments b
      JOIN insurance_coverage c ON c.treatment_id = b.treatment_id
     WHERE c.policy_id = NEW.policy_id;

    v_requested := CASE WHEN NEW.status = 'Pending' THEN NEW.claim_amount
                        ELSE NEW.approved_amount END;
    IF v_eligible <= 0 OR v_requested > v_eligible THEN
        RAISE EXCEPTION 'Claim reservation exceeds eligible treatment coverage for the visit'
            USING ERRCODE = 'check_violation';
    END IF;

    SELECT COALESCE(SUM(CASE WHEN c.status = 'Pending' THEN c.claim_amount
                            WHEN c.status = 'Approved' THEN c.approved_amount ELSE 0 END), 0),
           COALESCE(SUM(CASE WHEN c.policy_id = NEW.policy_id THEN
                            CASE WHEN c.status = 'Pending' THEN c.claim_amount
                                 WHEN c.status = 'Approved' THEN c.approved_amount ELSE 0 END
                            ELSE 0 END), 0)
      INTO v_reserved, v_policy_reserved
      FROM insurance_claim c
     WHERE c.invoice_id = NEW.invoice_id AND c.claim_id IS DISTINCT FROM NEW.claim_id;
    IF v_policy_reserved + v_requested > v_eligible
       OR v_reserved + v_requested > v_invoice_total THEN
        RAISE EXCEPTION 'Pending and approved claims exceed policy coverage or invoice total'
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$$;

-- The old trigger omitted status: a status-only update must also be validated.

CREATE OR REPLACE FUNCTION fn_validate_doctor_payment()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_appointment_doctor INTEGER;
    v_invoice_id INTEGER;
BEGIN
    SELECT doctor_id INTO v_appointment_doctor
      FROM appointment
     WHERE appointment_id = NEW.appointment_id;
    IF v_appointment_doctor IS DISTINCT FROM NEW.doctor_id THEN
        RAISE EXCEPTION 'Doctor payment must reference the doctor assigned to the appointment'
            USING ERRCODE = 'check_violation';
    END IF;
    IF NEW.doctor_payment <= 0 THEN
        RAISE EXCEPTION 'Doctor compensation must be greater than zero'
            USING ERRCODE = 'check_violation';
    END IF;

    IF NEW.invoice_item_id IS NOT NULL THEN
        SELECT i.invoice_id INTO v_invoice_id
          FROM invoice_item ii
          JOIN invoice i ON i.invoice_id = ii.invoice_id
         WHERE ii.invoice_item_id = NEW.invoice_item_id
           AND i.appointment_id = NEW.appointment_id;
        IF v_invoice_id IS NULL THEN
            RAISE EXCEPTION 'Doctor payment invoice item must belong to the appointment invoice'
                USING ERRCODE = 'check_violation';
        END IF;
    END IF;
    RETURN NEW;
END;
$$;
