-- MedSync CATMS - Foreign Key Constraints (03_constraints.sql)
-- Target: PostgreSQL 16+ (Neon Cloud / Local)
-- Deferred constraints to resolve circular foreign key dependencies

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'branch'::regclass AND conname = 'fk_branch_manager_staff'
    ) THEN
        ALTER TABLE branch ADD CONSTRAINT fk_branch_manager_staff
            FOREIGN KEY (manager_staff_id) REFERENCES staff(staff_id);
    END IF;
END;
$$;
