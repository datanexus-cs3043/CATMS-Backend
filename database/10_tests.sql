-- Post-seed smoke checks for the original CATMS schema plus database extensions.

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
          FROM information_schema.columns
         WHERE table_schema = current_schema()
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

    IF EXISTS (
        SELECT 1 FROM appointment a JOIN doctor d USING (doctor_id)
        JOIN staff s USING (staff_id) WHERE a.branch_id <> s.branch_id
    ) THEN
        RAISE EXCEPTION 'Appointment branch differs from assigned doctor branch';
    END IF;

    IF EXISTS (
        SELECT 1 FROM branch b JOIN staff s ON s.staff_id=b.manager_staff_id
        WHERE b.branch_id<>s.branch_id
    ) THEN
        RAISE EXCEPTION 'Branch manager belongs to another branch';
    END IF;

    IF EXISTS (
        SELECT 1 FROM insurance_claim c JOIN invoice i USING (invoice_id)
        JOIN appointment a USING (appointment_id) JOIN insurance_policy p USING (policy_id)
        WHERE a.patient_id<>p.patient_id OR c.status NOT IN ('Pending','Approved','Rejected')
        OR (c.status<>'Approved' AND c.approved_amount<>0)
    ) THEN
        RAISE EXCEPTION 'Claim ownership or status/approval is inconsistent';
    END IF;

    IF EXISTS (
        SELECT 1 FROM invoice i JOIN appointment a USING (appointment_id)
        JOIN staff s USING (staff_id) WHERE a.branch_id<>s.branch_id
    ) OR EXISTS (
        SELECT 1 FROM patient_payment pp JOIN invoice i USING (invoice_id)
        JOIN appointment a USING (appointment_id) JOIN staff s ON s.staff_id=pp.received_by
        WHERE a.branch_id<>s.branch_id
    ) THEN
        RAISE EXCEPTION 'Invoice or receipt staff belongs to another branch';
    END IF;

    IF to_regclass('v_branch_daily_appointment_summary') IS NULL
       OR to_regclass('v_doctor_revenue') IS NULL
       OR to_regclass('v_outstanding_balances') IS NULL
       OR to_regclass('v_treatment_category_usage') IS NULL
       OR to_regclass('v_insurance_vs_out_of_pocket') IS NULL THEN
        RAISE EXCEPTION 'One or more required reporting views are missing';
    END IF;
END;
$$;
