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


CREATE OR REPLACE PROCEDURE sp_complete_appointment(p_appointment_id INTEGER)
LANGUAGE plpgsql
AS $$
DECLARE
    v_appointment appointment%ROWTYPE;
BEGIN
    SELECT * INTO v_appointment
      FROM appointment
     WHERE appointment_id = p_appointment_id
     FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Appointment % does not exist', p_appointment_id
            USING ERRCODE = 'foreign_key_violation';
    END IF;
    IF v_appointment.status <> 'Scheduled' THEN
        RAISE EXCEPTION 'Only scheduled appointments can be completed'
            USING ERRCODE = 'check_violation';
    END IF;
    IF v_appointment.treatment_id IS NULL
       AND NOT EXISTS (
           SELECT 1 FROM appointment_treatment
            WHERE appointment_id = p_appointment_id
       )
       AND NOT EXISTS (
           SELECT 1 FROM consultation_note
            WHERE appointment_id = p_appointment_id
       )
       AND NOT EXISTS (
           SELECT 1 FROM invoice i
           JOIN invoice_item ii ON ii.invoice_id = i.invoice_id
            WHERE i.appointment_id = p_appointment_id
       ) THEN
        RAISE EXCEPTION 'A completed appointment requires a treatment or consultation note'
            USING ERRCODE = 'check_violation';
    END IF;
    UPDATE appointment
       SET status = 'Completed'
     WHERE appointment_id = p_appointment_id;
END;
$$;

CREATE OR REPLACE PROCEDURE sp_cancel_appointment(p_appointment_id INTEGER)
LANGUAGE plpgsql
AS $$
DECLARE
    v_status VARCHAR(20);
BEGIN
    SELECT status INTO v_status
      FROM appointment
     WHERE appointment_id = p_appointment_id
     FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Appointment % does not exist', p_appointment_id
            USING ERRCODE = 'foreign_key_violation';
    END IF;
    IF v_status <> 'Scheduled' THEN
        RAISE EXCEPTION 'Only scheduled appointments can be cancelled'
            USING ERRCODE = 'check_violation';
    END IF;
    UPDATE appointment
       SET status = 'Cancelled'
     WHERE appointment_id = p_appointment_id;
END;
$$;
