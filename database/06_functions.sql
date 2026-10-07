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