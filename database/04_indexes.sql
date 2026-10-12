-- MedSync CATMS - Database Indexes (04_indexes.sql)
-- Target: PostgreSQL 16+ (Neon Cloud / Local)
-- Secondary indexes for foreign-key lookups and query performance

CREATE INDEX IF NOT EXISTS idx_users_logins_user_id ON users_logins(user_id);
CREATE INDEX IF NOT EXISTS idx_staff_branch_id ON staff(branch_id);
CREATE INDEX IF NOT EXISTS idx_staff_users_logins_id ON staff(users_logins_id);
CREATE INDEX IF NOT EXISTS idx_patient_branch_id ON patient(branch_id);
CREATE INDEX IF NOT EXISTS idx_emergency_contact_patient_id ON emergency_contact(patient_id);
CREATE INDEX IF NOT EXISTS idx_policy_patient_id ON insurance_policy(patient_id);
CREATE INDEX IF NOT EXISTS idx_policy_provider_id ON insurance_policy(provider_id);
CREATE INDEX IF NOT EXISTS idx_treatment_category_id ON treatment(category_id);
CREATE INDEX IF NOT EXISTS idx_doctor_staff_id ON doctor(staff_id);
-- The API trims names; also protect direct writes with surrounding spaces.
CREATE UNIQUE INDEX IF NOT EXISTS uq_specialty_name_normalized ON specialty (LOWER(BTRIM(specialty_name)));
CREATE INDEX IF NOT EXISTS idx_appointment_patient_id ON appointment(patient_id);
CREATE INDEX IF NOT EXISTS idx_appointment_doctor_id ON appointment(doctor_id);
CREATE INDEX IF NOT EXISTS idx_appointment_branch_id ON appointment(branch_id);
CREATE INDEX IF NOT EXISTS idx_appointment_treatment_id ON appointment(treatment_id);
CREATE INDEX IF NOT EXISTS idx_invoice_appointment_id ON invoice(appointment_id);
CREATE INDEX IF NOT EXISTS idx_invoice_staff_id ON invoice(staff_id);
CREATE INDEX IF NOT EXISTS idx_invoice_item_invoice_id ON invoice_item(invoice_id);
CREATE INDEX IF NOT EXISTS idx_invoice_item_treatment_id ON invoice_item(treatment_id);
CREATE INDEX IF NOT EXISTS idx_consultation_note_appointment_id ON consultation_note(appointment_id);
CREATE INDEX IF NOT EXISTS idx_insurance_coverage_policy_id ON insurance_coverage(policy_id);
CREATE INDEX IF NOT EXISTS idx_insurance_coverage_treatment_id ON insurance_coverage(treatment_id);
CREATE INDEX IF NOT EXISTS idx_insurance_claim_invoice_id ON insurance_claim(invoice_id);
CREATE INDEX IF NOT EXISTS idx_insurance_claim_policy_id ON insurance_claim(policy_id);
CREATE INDEX IF NOT EXISTS idx_doctor_payment_doctor_id ON doctor_payment(doctor_id);
CREATE INDEX IF NOT EXISTS idx_doctor_payment_appointment_id ON doctor_payment(appointment_id);
CREATE INDEX IF NOT EXISTS idx_doctor_payment_invoice_item_id ON doctor_payment(invoice_item_id);
CREATE INDEX IF NOT EXISTS idx_patient_user_id ON patient(user_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_appointment_primary_treatment
    ON appointment_treatment(appointment_id)
    WHERE is_primary;
CREATE INDEX IF NOT EXISTS idx_appointment_treatment_treatment
    ON appointment_treatment(treatment_id);
CREATE INDEX IF NOT EXISTS idx_patient_payment_invoice_date
    ON patient_payment(invoice_id, payment_date);

-- Branch/date lists and doctor/date slot lookups are the primary scheduling reads.
CREATE INDEX IF NOT EXISTS idx_appointment_branch_date ON appointment(branch_id, appointment_date, appointment_id);
CREATE INDEX IF NOT EXISTS idx_appointment_doctor_date ON appointment(doctor_id, appointment_date, start_time) WHERE status <> 'Cancelled';
CREATE INDEX IF NOT EXISTS idx_invoice_date ON invoice(invoice_date, invoice_id);
