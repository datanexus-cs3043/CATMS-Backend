-- Post-seed smoke checks for the original CATMS schema plus database extensions.

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
          FROM information_schema.columns
         WHERE table_schema = 'public'
           AND table_name = 'appointment'
           AND column_name = 'status'
    ) THEN
        RAISE EXCEPTION 'Appointment status extension was not installed';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
         WHERE conname = 'ex_appointment_doctor_time'
           AND conrelid = 'appointment'::regclass
    ) THEN
        RAISE EXCEPTION 'Doctor appointment overlap constraint is missing';
    END IF;

    IF (SELECT COUNT(*) FROM branch) < 3 THEN
        RAISE EXCEPTION 'Expected sample branches for Colombo, Kandy, and Galle';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM appointment WHERE status = 'Completed') THEN
        RAISE EXCEPTION 'Expected completed appointment samples';
    END IF;

    IF EXISTS (
        SELECT 1 FROM appointment
         WHERE status NOT IN ('Scheduled', 'Completed', 'Cancelled')
            OR status IS NULL
    ) THEN
        RAISE EXCEPTION 'Appointment statuses are outside the supported lifecycle';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM appointment_treatment) THEN
        RAISE EXCEPTION 'Appointment treatment assignments are missing';
    END IF;
    
    IF EXISTS (
        SELECT 1
          FROM appointment a
         WHERE a.treatment_id IS NOT NULL
           AND NOT EXISTS (
               SELECT 1
                 FROM appointment_treatment apt
                WHERE apt.appointment_id = a.appointment_id
                  AND apt.treatment_id = a.treatment_id
                  AND apt.is_primary
           )
    ) THEN
        RAISE EXCEPTION 'Legacy appointment treatment links were not synchronized';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM patient_payment)
       OR NOT EXISTS (SELECT 1 FROM invoice WHERE balance > 0)
       OR NOT EXISTS (SELECT 1 FROM insurance_claim) THEN
        RAISE EXCEPTION 'Expected payment ledger, outstanding balance, and insurance claim samples';
    END IF;

    IF EXISTS (
        SELECT 1
          FROM invoice i
          LEFT JOIN (
              SELECT invoice_id, SUM(amount) AS paid
                FROM patient_payment
               GROUP BY invoice_id
          ) p ON p.invoice_id = i.invoice_id
         WHERE i.amount_paid <> COALESCE(p.paid, 0)
    ) THEN
        RAISE EXCEPTION 'Invoice paid amounts do not reconcile to the patient payment ledger';
    END IF;

    IF EXISTS (
        SELECT 1
          FROM invoice i
          JOIN (
              SELECT invoice_id, SUM(quantity * unitprice) AS billed
                FROM invoice_item
               GROUP BY invoice_id
          ) t ON t.invoice_id = i.invoice_id
         WHERE i.amount_paid + i.balance <> t.billed
    ) THEN
        RAISE EXCEPTION 'Invoice balances do not reconcile to their invoice items';
    END IF;

    IF EXISTS (
        SELECT 1
          FROM appointment a
          JOIN appointment b
            ON b.doctor_id = a.doctor_id
           AND b.appointment_id > a.appointment_id
           AND b.status <> 'Cancelled'
           AND a.status <> 'Cancelled'
           AND a.appointment_date = b.appointment_date
           AND a.start_time < b.end_time
           AND a.end_time > b.start_time
    ) THEN
        RAISE EXCEPTION 'Overlapping active appointments exist for a doctor';
    END IF;

    IF to_regclass('public.v_branch_daily_appointment_summary') IS NULL
       OR to_regclass('public.v_doctor_revenue') IS NULL
       OR to_regclass('public.v_outstanding_balances') IS NULL
       OR to_regclass('public.v_treatment_category_usage') IS NULL
       OR to_regclass('public.v_insurance_vs_out_of_pocket') IS NULL THEN
        RAISE EXCEPTION 'One or more required reporting views are missing';
    END IF;
END;
$$;
