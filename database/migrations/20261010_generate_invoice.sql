-- 2026-10-10: run once in Neon after 05-08 are applied.
-- Adds sp_generate_invoice (same text as in 07_procedures.sql).
-- Builds the bill for a completed visit in one transaction: one invoice row plus one
-- invoice_item per recorded treatment (price copied when the treatment was recorded).
-- Triggers on invoice_item then set the total, balance and status automatically.
CREATE OR REPLACE PROCEDURE sp_generate_invoice(
    p_appointment_id INTEGER,
    p_staff_id INTEGER,
    INOUT p_invoice_id INTEGER DEFAULT NULL
)
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
    IF v_appointment.status <> 'Completed' THEN
        RAISE EXCEPTION 'Only completed appointments can be invoiced'
            USING ERRCODE = 'check_violation';
    END IF;
    IF EXISTS (SELECT 1 FROM invoice WHERE appointment_id = p_appointment_id) THEN
        RAISE EXCEPTION 'Appointment % already has an invoice', p_appointment_id
            USING ERRCODE = 'unique_violation';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM appointment_treatment WHERE appointment_id = p_appointment_id) THEN
        RAISE EXCEPTION 'Record at least one treatment before generating the invoice'
            USING ERRCODE = 'check_violation';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM staff
         WHERE staff_id = p_staff_id AND branch_id = v_appointment.branch_id
    ) THEN
        RAISE EXCEPTION 'Invoice staff must work at the appointment branch'
            USING ERRCODE = 'check_violation';
    END IF;

    INSERT INTO invoice (appointment_id, staff_id, invoice_date, amount_paid, balance, status)
    VALUES (p_appointment_id, p_staff_id, CURRENT_DATE, 0, 0, 'Unpaid')
    RETURNING invoice_id INTO p_invoice_id;

    INSERT INTO invoice_item (invoice_id, treatment_id, quantity, unitprice, description)
    SELECT p_invoice_id, at.treatment_id, at.quantity, at.unitprice, t.treatment_name
      FROM appointment_treatment at
      JOIN treatment t ON t.treatment_id = at.treatment_id
     WHERE at.appointment_id = p_appointment_id
     ORDER BY at.appointment_treatment_id;
END;
$$;
