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