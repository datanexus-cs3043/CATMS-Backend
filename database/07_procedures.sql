-- MedSync CATMS - Stored Procedures (07_procedures.sql)
-- Target: PostgreSQL 16+ (Neon Cloud / Local)

-- Transactional operations for appointment lifecycle and patient receipts.
-- Requires the schema extensions in 05_views.sql. Receipt reconciliation must
-- be supplied by the patient-payment triggers; API authorization is separate.

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
    v_paid NUMERIC(10, 2);
    v_new_balance NUMERIC(10, 2);
    v_new_paid NUMERIC(10, 2);
BEGIN
    IF p_amount IS NULL OR p_amount NOT BETWEEN 0.01 AND 99999999.99
       OR p_amount <> ROUND(p_amount, 2) THEN
        RAISE EXCEPTION 'Payment amount must be positive, within range, and have at most two decimal places'
            USING ERRCODE = 'check_violation';
    END IF;

    SELECT balance, amount_paid INTO v_balance, v_paid
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
         COALESCE(NULLIF(BTRIM(p_payment_method), ''), 'Cash'),
         p_reference_number, 'Payment', p_received_by);

    -- Fail atomically if the reconciliation triggers are absent or inconsistent.
    -- Merely recording a receipt must not leave the old balance available again.
    SELECT balance, amount_paid INTO v_new_balance, v_new_paid
      FROM invoice WHERE invoice_id = p_invoice_id;
    IF v_new_balance IS DISTINCT FROM v_balance - p_amount
       OR v_new_paid IS DISTINCT FROM v_paid + p_amount THEN
        RAISE EXCEPTION 'Patient-payment reconciliation is required for invoice %', p_invoice_id
            USING ERRCODE = 'check_violation';
    END IF;
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
    IF v_appointment.status IS DISTINCT FROM 'Scheduled' THEN
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
    IF v_status IS DISTINCT FROM 'Scheduled' THEN
        RAISE EXCEPTION 'Only scheduled appointments can be cancelled'
            USING ERRCODE = 'check_violation';
    END IF;
    UPDATE appointment
       SET status = 'Cancelled'
     WHERE appointment_id = p_appointment_id;
END;
$$;

CREATE OR REPLACE PROCEDURE sp_reschedule_appointment(
    p_appointment_id INTEGER,
    p_appointment_date DATE,
    p_start_time TIME,
    p_end_time TIME,
    p_created_by VARCHAR(150)
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_appointment appointment%ROWTYPE;
    v_new_appointment_id INTEGER;
BEGIN
    IF p_appointment_date IS NULL OR p_start_time IS NULL OR p_end_time IS NULL
       OR p_end_time <= p_start_time THEN
        RAISE EXCEPTION 'A date and valid start/end times are required'
            USING ERRCODE = 'check_violation';
    END IF;
    IF p_created_by IS NULL OR BTRIM(p_created_by) = '' OR LENGTH(p_created_by) > 150 THEN
        RAISE EXCEPTION 'A nonblank creator identifier of at most 150 characters is required'
            USING ERRCODE = 'check_violation';
    END IF;

    SELECT * INTO v_appointment
      FROM appointment
     WHERE appointment_id = p_appointment_id
     FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Appointment % does not exist', p_appointment_id
            USING ERRCODE = 'foreign_key_violation';
    END IF;
    IF v_appointment.status IS DISTINCT FROM 'Scheduled' THEN
        RAISE EXCEPTION 'Only scheduled appointments can be rescheduled'
            USING ERRCODE = 'check_violation';
    END IF;
    IF EXISTS (
        SELECT 1
          FROM appointment
         WHERE original_appointment_id = p_appointment_id
    ) THEN
        RAISE EXCEPTION 'Appointment % has already been rescheduled', p_appointment_id
            USING ERRCODE = 'unique_violation';
    END IF;
    -- Serialize bookings for this doctor before checking the new slot.
    PERFORM doctor_id FROM doctor
     WHERE doctor_id = v_appointment.doctor_id FOR UPDATE;
    IF EXISTS (
        SELECT 1 FROM appointment
         WHERE doctor_id = v_appointment.doctor_id
           AND appointment_date = p_appointment_date
           AND appointment_id <> p_appointment_id
           AND status = 'Scheduled'
           AND start_time < p_end_time AND end_time > p_start_time
    ) THEN
        RAISE EXCEPTION 'The doctor already has an appointment in this time slot'
            USING ERRCODE = 'check_violation';
    END IF;

    -- Keep the replacement and old-slot release in the same transaction.
    INSERT INTO appointment (
        patient_id, doctor_id, branch_id, appointment_date, start_time, end_time,
        appointment_type, created_by, original_appointment_id, treatment_id
    ) VALUES (
        v_appointment.patient_id, v_appointment.doctor_id, v_appointment.branch_id,
        p_appointment_date, p_start_time, p_end_time,
        v_appointment.appointment_type, p_created_by, p_appointment_id,
        v_appointment.treatment_id
    ) RETURNING appointment_id INTO v_new_appointment_id;

    INSERT INTO appointment_treatment
        (appointment_id, treatment_id, quantity, unitprice, is_primary)
    SELECT v_new_appointment_id, treatment_id, quantity, unitprice, is_primary
      FROM appointment_treatment WHERE appointment_id = p_appointment_id
    ON CONFLICT (appointment_id, treatment_id) DO UPDATE
       SET quantity = EXCLUDED.quantity, unitprice = EXCLUDED.unitprice,
           is_primary = EXCLUDED.is_primary;

    UPDATE appointment SET status = 'Cancelled'
     WHERE appointment_id = p_appointment_id;
END;
$$;
