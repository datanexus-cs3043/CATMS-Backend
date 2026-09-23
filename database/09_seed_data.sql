-- MedSync CATMS - Database Seed Data (09_seed_data.sql)
-- Target: PostgreSQL 16+ (Neon Cloud / Local Docker)
-- Populated with standardized mock data and Argon2id hashed credentials

BEGIN;

-- ============================================================================
-- Data for table: branch (3 records)
-- ============================================================================
INSERT INTO branch (branch_id, branch_name, location, contact_details) VALUES
    (1, 'MedSync Colombo', 'Colombo', '0112345678'),
    (2, 'MedSync Kandy', 'Kandy', '0812345678'),
    (3, 'MedSync Galle', 'Galle', '0912345678');


-- ============================================================================
-- Data for table: user (7 records)
-- ============================================================================
INSERT INTO "user" (user_id, first_name, last_name, contact_details, email, username, password) VALUES
    (1, 'Nayanajith', 'Bandara', '0712345678', 'nayanajith@example.com', 'nayanajith', '$argon2id$v=19$m=65536,t=3,p=4$fkG7GP1I9bpNDgJNj63RKQ$Vbk5/aA+CKdyG1zo0B+6V2qIt0nOgEvKrIU44yu7waU'),
    (2, 'Adithya', 'Perera', '0723456789', 'adithya@example.com', 'adithya', '$argon2id$v=19$m=65536,t=3,p=4$NcIvTFcX2PX/9HFcnoSBYA$WcObeqccKZhgGlwTC5jojTncEetbHzZthyen9t+rDUU'),
    (3, 'Shashika', 'Fernando', '0734567890', 'shashika@example.com', 'shashika', '$argon2id$v=19$m=65536,t=3,p=4$zfY8PhRzBTANffZMCHEaRQ$Zz1R8Hp/bC5S0fhxoEmBqvu5HUFNornXajWPMMjO8r8'),
    (4, 'Tharushi', 'Silva', '0745678901', 'tharushi@example.com', 'tharushi', '$argon2id$v=19$m=65536,t=3,p=4$E4Yavzd4QBjSJtUZgZdjtg$tunNabruAz7hNDJxDHjIEOdPa3vGnDeydBUM/pvrk6c'),
    (5, 'Kavindu', 'Perera', '0751234567', 'kavindu@example.com', 'kavindu', '$argon2id$v=19$m=65536,t=3,p=4$At0nsCS/m1L2hlFSqyf/uA$tU61+KfRigqdgxwloJFK6pNDJlpYnKpy3PsbjfahmK4'),
    (6, 'Amaya', 'Fernando', '0762345678', 'amaya@example.com', 'amaya', '$argon2id$v=19$m=65536,t=3,p=4$Gp+GNtILOAeEggebg3WWJw$M+FYeyAEBn4NkcJ2fbVOOoH4QJgI+JZ3lPax3Q4P59k'),
    (7, 'Sahan', 'Silva', '0773456789', 'parent@example.com', 'sahan', '$argon2id$v=19$m=65536,t=3,p=4$XAE/N0gLe9elLcSqvwv4EA$RajB9CFv4cVSXo0T8/XIDm61r4kGtaChXXTnQJmECRs');


-- ============================================================================
-- Data for table: users_logins (10 records)
-- ============================================================================
INSERT INTO users_logins (users_logins_id, user_id, login_time, user_name) VALUES
    (1, 1, '2026-09-20 17:12:38.861986', 'nayanajith'),
    (2, 2, '2026-09-20 17:12:38.861986', 'adithya'),
    (3, 3, '2026-09-20 17:12:38.861986', 'shashika'),
    (4, 4, '2026-09-20 17:12:38.861986', 'tharushi'),
    (5, 2, '2026-09-20 17:50:47.953046', 'adithya'),
    (6, 2, '2026-09-20 17:53:52.923567', 'adithya'),
    (7, 2, '2026-09-20 18:05:45.290534', 'adithya'),
    (8, 7, '2026-09-20 18:06:23.240820', 'sahan'),
    (9, 2, '2026-09-20 18:19:46.305421', 'adithya'),
    (10, 3, '2026-09-20 20:57:01.794676', 'shashika');


-- ============================================================================
-- Data for table: staff (4 records)
-- ============================================================================
INSERT INTO staff (staff_id, branch_id, users_logins_id, first_name, last_name, contact_details, email, staff_type, role) VALUES
    (1, 1, 1, 'Nayanajith', 'Bandara', '0712345678', 'nayanajith@example.com', 'Medical', 'Doctor'),
    (2, 1, 2, 'Adithya', 'Perera', '0723456789', 'adithya@example.com', 'Medical', 'Doctor'),
    (3, 2, 3, 'Shashika', 'Fernando', '0734567890', 'shashika@example.com', 'Non-Medical', 'Receptionist'),
    (4, 3, 4, 'Tharushi', 'Silva', '0745678901', 'tharushi@example.com', 'Non-Medical', 'Manager');


-- Update branch manager staff references (deferred to avoid circular FK)
UPDATE branch SET manager_staff_id = 4 WHERE branch_id = 3;

-- ============================================================================
-- Data for table: treatment_category (3 records)
-- ============================================================================
INSERT INTO treatment_category (category_id, category_name, description) VALUES
    (1, 'General Medicine', 'General medical treatments'),
    (2, 'ENT', 'Ear, nose and throat treatments'),
    (3, 'Paediatrics', 'Medical treatments for children');


-- ============================================================================
-- Data for table: treatment (5 records)
-- ============================================================================
INSERT INTO treatment (treatment_id, category_id, service_code, treatment_name, standard_price) VALUES
    (1, 1, 'GEN001', 'General Consultation', 2500.00),
    (2, 1, 'GEN002', 'Medical Checkup', 4000.00),
    (3, 2, 'ENT001', 'ENT Consultation', 3000.00),
    (4, 2, 'ENT002', 'Ear Examination', 3500.00),
    (5, 3, 'PED001', 'Paediatric Consultation', 3000.00);


-- ============================================================================
-- Data for table: specialty (3 records)
-- ============================================================================
INSERT INTO specialty (specialty_id, specialty_name, description) VALUES
    (1, 'General Medicine', 'General medical specialty'),
    (2, 'ENT', 'Ear, nose and throat specialty'),
    (3, 'Paediatrics', 'Medical specialty for children');


-- ============================================================================
-- Data for table: doctor (2 records)
-- ============================================================================
INSERT INTO doctor (doctor_id, staff_id, doctor_name, doctor_license_number) VALUES
    (1, 1, 'Dr. Nayanajith Bandara', 'SLMC10001'),
    (2, 2, 'Dr. Adithya Perera', 'SLMC10002');


-- ============================================================================
-- Data for table: doctor_specialty (4 records)
-- ============================================================================
INSERT INTO doctor_specialty (doctor_id, specialty_id) VALUES
    (1, 1),
    (1, 2),
    (2, 1),
    (2, 3);


-- ============================================================================
-- Data for table: insurance_provider (2 records)
-- ============================================================================
INSERT INTO insurance_provider (provider_id, provider_name, contact_details) VALUES
    (1, 'Ceylinco Insurance', '0113456789'),
    (2, 'Sri Lanka Insurance', '0114567890');


-- ============================================================================
-- Data for table: patient (3 records)
-- ============================================================================
INSERT INTO patient (patient_id, branch_id, first_name, last_name, date_of_birth, gender, patient_type, contact_details, email, address, user_id) VALUES
    (1, 1, 'Kavindu', 'Perera', '2002-05-15', 'Male', 'Regular', '0751234567', 'kavindu@example.com', 'Colombo', 5),
    (2, 2, 'Amaya', 'Fernando', '1998-08-22', 'Female', 'Regular', '0762345678', 'amaya@example.com', 'Kandy', 6),
    (3, 3, 'Sahan', 'Silva', '2015-03-10', 'Male', 'Child', '0773456789', 'parent@example.com', 'Galle', 7);


-- ============================================================================
-- Data for table: emergency_contact (3 records)
-- ============================================================================
INSERT INTO emergency_contact (emergency_contact_id, patient_id, contact_name, relationship, phone) VALUES
    (1, 1, 'Sunil Perera', 'Father', '0711111111'),
    (2, 2, 'Nimali Fernando', 'Mother', '0722222222'),
    (3, 3, 'Kasun Silva', 'Father', '0733333333');


-- ============================================================================
-- Data for table: insurance_policy (2 records)
-- ============================================================================
INSERT INTO insurance_policy (policy_id, patient_id, provider_id, policy_number, start_date, end_date, status) VALUES
    (1, 1, 1, 100001, '2026-01-01', '2026-12-31', 'Active'),
    (2, 2, 2, 100002, '2026-01-01', '2026-12-31', 'Active');


-- ============================================================================
-- Data for table: insurance_coverage (3 records)
-- ============================================================================
INSERT INTO insurance_coverage (coverage_id, policy_id, treatment_id, coverage_percentage, maximum_amount) VALUES
    (1, 1, 1, 80.00, 2000.00),
    (2, 1, 2, 75.00, 3000.00),
    (3, 2, 3, 80.00, 2500.00);


-- ============================================================================
-- Data for table: appointment (3 records)
-- ============================================================================
INSERT INTO appointment (appointment_id, patient_id, doctor_id, branch_id, appointment_date, start_time, end_time, appointment_type, created_by, original_appointment_id, treatment_id) VALUES
    (1, 1, 1, 1, '2026-09-21', '09:00:00', '09:30:00', 'Consultation', 'shashika', NULL, 1),
    (2, 2, 2, 2, '2026-09-21', '10:00:00', '10:30:00', 'Consultation', 'shashika', NULL, 3),
    (3, 3, 2, 3, '2026-09-22', '11:00:00', '11:30:00', 'Consultation', 'tharushi', NULL, 5);


-- ============================================================================
-- Data for table: consultation_note (3 records)
-- ============================================================================
INSERT INTO consultation_note (note_id, appointment_id, note_content, created_at) VALUES
    (1, 1, 'Patient attended general medical consultation.', '2026-09-20 17:12:43.508115'),
    (2, 2, 'Patient attended ENT consultation.', '2026-09-20 17:12:43.508115'),
    (3, 3, 'Paediatric consultation completed.', '2026-09-20 17:12:43.508115');


-- ============================================================================
-- Data for table: invoice (3 records)
-- ============================================================================
INSERT INTO invoice (invoice_id, appointment_id, staff_id, invoice_date, amount_paid, balance, status) VALUES
    (1, 1, 3, '2026-09-21', 2500.00, 0.00, 'Paid'),
    (2, 2, 3, '2026-09-21', 1500.00, 1500.00, 'Partially Paid'),
    (3, 3, 4, '2026-09-22', 3000.00, 0.00, 'Paid');


-- ============================================================================
-- Data for table: invoice_item (3 records)
-- ============================================================================
INSERT INTO invoice_item (invoice_item_id, invoice_id, treatment_id, quantity, unitprice, description) VALUES
    (1, 1, 1, 1, 2500.00, 'General Consultation'),
    (2, 2, 3, 1, 3000.00, 'ENT Consultation'),
    (3, 3, 5, 1, 3000.00, 'Paediatric Consultation');


-- ============================================================================
-- Data for table: doctor_payment (3 records)
-- ============================================================================
INSERT INTO doctor_payment (doctor_payment_id, doctor_id, appointment_id, invoice_item_id, date, time, doctor_payment) VALUES
    (1, 1, 1, 1, '2026-09-21', '09:30:00', 1500.00),
    (2, 2, 2, 2, '2026-09-21', '10:30:00', 1800.00),
    (3, 2, 3, 3, '2026-09-22', '11:30:00', 1800.00);


-- ============================================================================
-- Data for table: insurance_claim (2 records)
-- ============================================================================
INSERT INTO insurance_claim (claim_id, invoice_id, policy_id, claim_date, claim_amount, approved_amount, status) VALUES
    (1, 1, 1, '2026-09-21', 2000.00, 2000.00, 'Approved'),
    (2, 2, 2, '2026-09-21', 2500.00, 0.00, 'Pending');


-- ============================================================================
-- Synchronize Identity Column Sequences
-- ============================================================================
SELECT setval(pg_get_serial_sequence('branch', 'branch_id'), COALESCE(MAX(branch_id), 1)) FROM branch;
SELECT setval(pg_get_serial_sequence('"user"', 'user_id'), COALESCE(MAX(user_id), 1)) FROM "user";
SELECT setval(pg_get_serial_sequence('users_logins', 'users_logins_id'), COALESCE(MAX(users_logins_id), 1)) FROM users_logins;
SELECT setval(pg_get_serial_sequence('staff', 'staff_id'), COALESCE(MAX(staff_id), 1)) FROM staff;
SELECT setval(pg_get_serial_sequence('treatment_category', 'category_id'), COALESCE(MAX(category_id), 1)) FROM treatment_category;
SELECT setval(pg_get_serial_sequence('treatment', 'treatment_id'), COALESCE(MAX(treatment_id), 1)) FROM treatment;
SELECT setval(pg_get_serial_sequence('specialty', 'specialty_id'), COALESCE(MAX(specialty_id), 1)) FROM specialty;
SELECT setval(pg_get_serial_sequence('doctor', 'doctor_id'), COALESCE(MAX(doctor_id), 1)) FROM doctor;
SELECT setval(pg_get_serial_sequence('insurance_provider', 'provider_id'), COALESCE(MAX(provider_id), 1)) FROM insurance_provider;
SELECT setval(pg_get_serial_sequence('patient', 'patient_id'), COALESCE(MAX(patient_id), 1)) FROM patient;
SELECT setval(pg_get_serial_sequence('emergency_contact', 'emergency_contact_id'), COALESCE(MAX(emergency_contact_id), 1)) FROM emergency_contact;
SELECT setval(pg_get_serial_sequence('insurance_policy', 'policy_id'), COALESCE(MAX(policy_id), 1)) FROM insurance_policy;
SELECT setval(pg_get_serial_sequence('insurance_coverage', 'coverage_id'), COALESCE(MAX(coverage_id), 1)) FROM insurance_coverage;
SELECT setval(pg_get_serial_sequence('appointment', 'appointment_id'), COALESCE(MAX(appointment_id), 1)) FROM appointment;
SELECT setval(pg_get_serial_sequence('consultation_note', 'note_id'), COALESCE(MAX(note_id), 1)) FROM consultation_note;
SELECT setval(pg_get_serial_sequence('invoice', 'invoice_id'), COALESCE(MAX(invoice_id), 1)) FROM invoice;
SELECT setval(pg_get_serial_sequence('invoice_item', 'invoice_item_id'), COALESCE(MAX(invoice_item_id), 1)) FROM invoice_item;
SELECT setval(pg_get_serial_sequence('doctor_payment', 'doctor_payment_id'), COALESCE(MAX(doctor_payment_id), 1)) FROM doctor_payment;
SELECT setval(pg_get_serial_sequence('insurance_claim', 'claim_id'), COALESCE(MAX(claim_id), 1)) FROM insurance_claim;

COMMIT;
