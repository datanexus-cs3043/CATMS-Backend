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
