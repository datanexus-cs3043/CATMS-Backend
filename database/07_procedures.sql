-- MedSync CATMS - Stored Procedures (07_procedures.sql)
-- Target: PostgreSQL 16+ (Neon Cloud / Local)

-- Transactional operations for appointment lifecycle and patient receipts.

CREATE OR REPLACE PROCEDURE sp_record_patient_payment(
    p_invoice_id INTEGER,
    p_amount NUMERIC(10, 2),
    p_payment_method VARCHAR(50) DEFAULT 'Cash',
    p_reference_number VARCHAR(100) DEFAULT NULL,
    p_received_by INTEGER DEFAULT NULL
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_balance NUMERIC(10, 2);
BEGIN
    IF p_amount IS NULL OR p_amount <= 0 THEN
        RAISE EXCEPTION 'Payment amount must be greater than zero'
            USING ERRCODE = 'check_violation';
    END IF;

    SELECT balance INTO v_balance
      FROM invoice
     WHERE invoice_id = p_invoice_id
     FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Invoice % does not exist', p_invoice_id
            USING ERRCODE = 'foreign_key_violation';
    END IF;
    IF p_amount > v_balance THEN
        RAISE EXCEPTION 'Payment amount (%) exceeds outstanding balance (%)',
            p_amount, v_balance
            USING ERRCODE = 'check_violation';
    END IF;

    INSERT INTO patient_payment
        (invoice_id, payment_date, amount, payment_method, reference_number, payment_type, received_by)
    VALUES
        (p_invoice_id, CURRENT_DATE, p_amount,
         COALESCE(NULLIF(p_payment_method, ''), 'Cash'),
         p_reference_number, 'Payment', p_received_by);
END;
$$;

