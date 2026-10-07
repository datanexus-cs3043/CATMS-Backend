-- Business rules and derived totals for the existing CATMS table contract.

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
BEGIN
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

    IF v_delta > 0 THEN
        INSERT INTO patient_payment
            (invoice_id, payment_date, amount, payment_method, payment_type)
        VALUES
            (NEW.invoice_id, NEW.invoice_date, v_delta, 'Invoice adjustment', 'Adjustment');
    ELSIF v_delta < 0 THEN
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
BEGIN
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