-- MedSync CATMS - Database Indexes (04_indexes.sql)
-- Target: PostgreSQL 16+ (Neon Cloud / Local)
-- Secondary indexes for foreign-key lookups and query performance

CREATE INDEX idx_users_logins_user_id ON users_logins(user_id);
CREATE INDEX idx_staff_branch_id ON staff(branch_id);
CREATE INDEX idx_staff_users_logins_id ON staff(users_logins_id);
CREATE INDEX idx_patient_branch_id ON patient(branch_id);
CREATE INDEX idx_emergency_contact_patient_id ON emergency_contact(patient_id);
CREATE INDEX idx_policy_patient_id ON insurance_policy(patient_id);
CREATE INDEX idx_policy_provider_id ON insurance_policy(provider_id);
CREATE INDEX idx_treatment_category_id ON treatment(category_id);
CREATE INDEX idx_doctor_staff_id ON doctor(staff_id);
CREATE INDEX idx_appointment_patient_id ON appointment(patient_id);
CREATE INDEX idx_appointment_doctor_id ON appointment(doctor_id);
CREATE INDEX idx_appointment_branch_id ON appointment(branch_id);
CREATE INDEX idx_appointment_treatment_id ON appointment(treatment_id);
CREATE INDEX idx_invoice_appointment_id ON invoice(appointment_id);
CREATE INDEX idx_invoice_staff_id ON invoice(staff_id);
CREATE INDEX idx_invoice_item_invoice_id ON invoice_item(invoice_id);
CREATE INDEX idx_invoice_item_treatment_id ON invoice_item(treatment_id);
CREATE INDEX idx_consultation_note_appointment_id ON consultation_note(appointment_id);
CREATE INDEX idx_insurance_coverage_policy_id ON insurance_coverage(policy_id);
CREATE INDEX idx_insurance_coverage_treatment_id ON insurance_coverage(treatment_id);
CREATE INDEX idx_insurance_claim_invoice_id ON insurance_claim(invoice_id);
CREATE INDEX idx_insurance_claim_policy_id ON insurance_claim(policy_id);
CREATE INDEX idx_doctor_payment_doctor_id ON doctor_payment(doctor_id);
CREATE INDEX idx_doctor_payment_appointment_id ON doctor_payment(appointment_id);
CREATE INDEX idx_doctor_payment_invoice_item_id ON doctor_payment(invoice_item_id);
