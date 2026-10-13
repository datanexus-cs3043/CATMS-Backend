BEGIN;
SET LOCAL TIME ZONE 'Asia/Colombo';
-- Sri Lankan demonstration dataset. Personal identities, addresses, clinic contacts,
-- licence identifiers, prices and coverage amounts are fictional; never contact
-- these records. Public insurer names are reference data, not product endorsements.
-- See SEED_DATA.md for sources, boundaries and setup instructions.
-- Reference tables are temporary so the same catalogue can support a reviewed
-- in-place maintenance operation without replaying the fresh-database seed.
CREATE TEMP TABLE seed_branch (n integer PRIMARY KEY, name text, location text, contact text) ON COMMIT DROP;
INSERT INTO seed_branch VALUES
(1,'MedSync Colombo','Colombo 07, Western Province','0112345678'),
(2,'MedSync Kandy','Peradeniya Road, Kandy, Central Province','0812345678'),
(3,'MedSync Galle','Matara Road, Galle, Southern Province','0912345678');
CREATE TEMP TABLE seed_category (n integer PRIMARY KEY, name text) ON COMMIT DROP;
INSERT INTO seed_category VALUES (1,'Consultations'),(2,'Specialist Care'),(3,'Laboratory and Diagnostics'),(4,'Therapy and Nutrition'),(5,'Minor Procedures and Wound Care'),(6,'Preventive Care');
CREATE TEMP TABLE seed_treatment (n integer PRIMARY KEY, name text, category integer, price numeric(10,2)) ON COMMIT DROP;
INSERT INTO seed_treatment VALUES
(1,'General Consultation',1,2500),
(2,'Medical Checkup',6,4000),
(3,'ENT Consultation',2,3000),
(4,'Ear Examination',2,3500),
(5,'Paediatric Consultation',2,3000),
(6,'Family Medicine Consultation',1,2500),
(7,'Family Medicine Follow-up',1,1800),
(8,'Cardiology Consultation',2,4500),
(9,'Cardiology Follow-up',2,3000),
(10,'Child Growth Assessment',2,2800),
(11,'Paediatric Follow-up',2,2200),
(12,'Dental Consultation',2,2500),
(13,'Dental Scaling',5,4500),
(14,'Dermatology Consultation',2,3500),
(15,'Dermatology Follow-up',2,2500),
(16,'Vision Assessment',3,1800),
(17,'Ophthalmology Consultation',2,3500),
(18,'Hearing Assessment',3,2500),
(19,'ENT Follow-up',2,2200),
(20,'Physiotherapy Assessment',4,3000),
(21,'Physiotherapy Session',4,2500),
(22,'Full Blood Count',3,1200),
(23,'Fasting Blood Sugar',3,600),
(24,'ECG Recording',3,1500),
(25,'Ultrasound Abdomen',3,5000),
(26,'Blood Pressure Review',6,800),
(27,'Preventive Health Review',6,2800),
(28,'Nutrition Consultation',4,2500),
(29,'Nutrition Follow-up',4,1800),
(30,'Orthopaedic Consultation',2,4000),
(31,'Orthopaedic Follow-up',2,2800),
(32,'Neurology Consultation',2,4500),
(33,'Neurology Follow-up',2,3200),
(34,'Respiratory Consultation',2,3500),
(35,'Spirometry',3,3000),
(36,'Gynaecology Consultation',2,3500),
(37,'Antenatal Review',2,3000),
(38,'Diabetes Review',1,2500),
(39,'HbA1c Test',3,2500),
(40,'Minor Procedure Review',5,2200),
(41,'Suture Removal',5,1500),
(42,'Wound Assessment',5,1800),
(43,'Wound Dressing',5,1200),
(44,'Post-treatment Review',1,2000),
(45,'Urine Full Report',3,800);
CREATE TEMP TABLE seed_specialty (n integer PRIMARY KEY, name text) ON COMMIT DROP;
INSERT INTO seed_specialty VALUES
(1,'General Medicine'),
(2,'ENT'),
(3,'Paediatrics'),
(4,'Family Medicine'),
(5,'Cardiology'),
(6,'Dentistry'),
(7,'Dermatology'),
(8,'Ophthalmology'),
(9,'Physiotherapy'),
(10,'Clinical Pathology'),
(11,'Radiology'),
(12,'Community Medicine'),
(13,'Clinical Nutrition'),
(14,'Orthopaedics'),
(15,'Neurology'),
(16,'Respiratory Medicine'),
(17,'Obstetrics and Gynaecology'),
(18,'Endocrinology'),
(19,'General Surgery'),
(20,'Rehabilitation Medicine'),
(21,'Urology'),
(22,'Rheumatology'),
(23,'Nephrology');
CREATE TEMP TABLE seed_provider (n integer PRIMARY KEY, name text, contact text) ON COMMIT DROP;
INSERT INTO seed_provider VALUES
(1,'Ceylinco General Insurance Limited','https://www.ceylinco-insurance.com'),
(2,'Sri Lanka Insurance Corporation General Limited','https://www.srilankainsurance.com'),
(3,'AIA Insurance Lanka Ltd','https://www.aialife.com.lk'),
(4,'Allianz Insurance Lanka Ltd','https://www.allianz.lk'),
(5,'Softlogic Life Insurance PLC','https://www.softlogiclife.lk'),
(6,'Union Assurance PLC','https://www.unionassurance.com');
CREATE TEMP TABLE seed_person (n integer PRIMARY KEY, first_name text, last_name text) ON COMMIT DROP;
INSERT INTO seed_person VALUES
(1,'Kasun','Perera'),
(2,'Dilini','Fernando'),
(3,'Chamith','Silva'),
(4,'Nethmi','Bandara'),
(5,'Ravindu','Jayasinghe'),
(6,'Ishara','Wijesinghe'),
(7,'Tharindu','Karunaratne'),
(8,'Sachini','Senanayake'),
(9,'Dinesh','Dissanayake'),
(10,'Hiruni','Abeywickrama'),
(11,'Pradeep','Gunasekara'),
(12,'Sanduni','Ranasinghe'),
(13,'Lahiru','Rajapaksha'),
(14,'Dinithi','De Silva'),
(15,'Roshan','Weerasinghe'),
(16,'Shanika','Herath'),
(17,'Imran','Hassan'),
(18,'Fathima','Nazeer'),
(19,'Arjun','Kumar'),
(20,'Nivetha','Sivakumar'),
(21,'Suresh','Ramanathan'),
(22,'Kavitha','Balasubramaniam'),
(23,'Mohamed','Farook'),
(24,'Ayesha','Rahman'),
(25,'Hasitha','Perera'),
(26,'Piumi','Fernando'),
(27,'Gayan','Silva'),
(28,'Chamari','Bandara'),
(29,'Ruwan','Jayasinghe'),
(30,'Malsha','Wijesinghe'),
(31,'Pasindu','Karunaratne'),
(32,'Thilini','Senanayake'),
(33,'Kasun','Abeywickrama'),
(34,'Dilini','Gunasekara'),
(35,'Chamith','Ranasinghe'),
(36,'Nethmi','Rajapaksha'),
(37,'Ravindu','De Silva'),
(38,'Ishara','Weerasinghe'),
(39,'Tharindu','Herath'),
(40,'Sachini','Hassan'),
(41,'Dinesh','Nazeer'),
(42,'Hiruni','Kumar'),
(43,'Pradeep','Sivakumar'),
(44,'Sanduni','Ramanathan'),
(45,'Lahiru','Balasubramaniam'),
(46,'Dinithi','Farook'),
(47,'Roshan','Rahman'),
(48,'Shanika','Perera'),
(49,'Imran','Fernando'),
(50,'Fathima','Silva'),
(51,'Arjun','Bandara'),
(52,'Nivetha','Jayasinghe'),
(53,'Suresh','Wijesinghe'),
(54,'Kavitha','Karunaratne'),
(55,'Mohamed','Senanayake'),
(56,'Ayesha','Dissanayake'),
(57,'Hasitha','Abeywickrama'),
(58,'Piumi','Gunasekara'),
(59,'Gayan','Ranasinghe'),
(60,'Chamari','Rajapaksha'),
(61,'Ruwan','De Silva'),
(62,'Malsha','Weerasinghe'),
(63,'Pasindu','Herath'),
(64,'Thilini','Hassan'),
(65,'Kasun','Kumar'),
(66,'Dilini','Sivakumar'),
(67,'Chamith','Ramanathan'),
(68,'Nethmi','Balasubramaniam'),
(69,'Ravindu','Farook'),
(70,'Ishara','Rahman'),
(71,'Tharindu','Perera'),
(72,'Sachini','Fernando'),
(73,'Dinesh','Silva'),
(74,'Hiruni','Bandara'),
(75,'Pradeep','Jayasinghe'),
(76,'Sanduni','Wijesinghe'),
(77,'Lahiru','Karunaratne'),
(78,'Dinithi','Senanayake'),
(79,'Roshan','Dissanayake'),
(80,'Shanika','Abeywickrama'),
(81,'Imran','Gunasekara'),
(82,'Fathima','Ranasinghe'),
(83,'Arjun','Rajapaksha'),
(84,'Nivetha','De Silva'),
(85,'Suresh','Weerasinghe'),
(86,'Kavitha','Herath'),
(87,'Mohamed','Hassan'),
(88,'Ayesha','Nazeer'),
(89,'Hasitha','Kumar'),
(90,'Piumi','Sivakumar'),
(91,'Gayan','Ramanathan'),
(92,'Chamari','Balasubramaniam'),
(93,'Ruwan','Farook'),
(94,'Malsha','Rahman'),
(95,'Pasindu','Perera'),
(96,'Thilini','Fernando'),
(97,'Kasun','Bandara'),
(98,'Dilini','Jayasinghe'),
(99,'Chamith','Wijesinghe'),
(100,'Nethmi','Karunaratne'),
(101,'Ravindu','Senanayake'),
(102,'Ishara','Dissanayake'),
(103,'Tharindu','Abeywickrama'),
(104,'Sachini','Gunasekara'),
(105,'Dinesh','Ranasinghe'),
(106,'Hiruni','Rajapaksha'),
(107,'Pradeep','De Silva'),
(108,'Sanduni','Weerasinghe'),
(109,'Lahiru','Herath'),
(110,'Dinithi','Hassan'),
(111,'Roshan','Nazeer'),
(112,'Shanika','Kumar'),
(113,'Imran','Sivakumar'),
(114,'Fathima','Ramanathan'),
(115,'Arjun','Balasubramaniam'),
(116,'Nivetha','Farook'),
(117,'Suresh','Rahman'),
(118,'Kavitha','Perera'),
(119,'Mohamed','Fernando'),
(120,'Ayesha','Silva');
-- FRESH DATABASE ONLY
DO $seed$
DECLARE
    i integer;
    j integer;
    v_user integer;
    v_login integer;
    v_staff integer;
    v_patient integer;
    v_policy integer;
    v_appt integer;
    v_invoice integer;
    v_item integer;
    v_role text;
    v_name seed_person%ROWTYPE;
    v_branch integer;
    v_day date;
    v_total numeric;
    v_username text;
    v_branches integer[];
    v_staffs integer[];
    v_doctors integer[];
    v_patients integer[];
    v_policies integer[];
    v_treatments integer[];
    v_categories integer[];
    v_specialties integer[];
    v_providers integer[];
BEGIN
    -- Refuse a populated target. Never overwrite records or reset identities.
    IF EXISTS (SELECT 1 FROM "user") OR EXISTS (SELECT 1 FROM branch)
       OR EXISTS (SELECT 1 FROM patient) OR EXISTS (SELECT 1 FROM treatment) THEN
        RAISE EXCEPTION 'Fresh seed requires an empty schema; use reviewed maintenance for an existing database';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname='pgcrypto') THEN
        RAISE EXCEPTION 'Install pgcrypto before seeding demonstration accounts';
    END IF;
    FOR i IN 1..3 LOOP
        INSERT INTO branch(branch_name,location,contact_details)
        SELECT name,location,contact FROM seed_branch WHERE n=i RETURNING branch_id INTO v_branch;
        v_branches:=array_append(v_branches,v_branch);
    END LOOP;
    FOR i IN 1..6 LOOP
        INSERT INTO treatment_category(category_name,description) SELECT name,'Clinic service catalogue' FROM seed_category WHERE n=i RETURNING category_id INTO j;
        v_categories:=array_append(v_categories,j);
        INSERT INTO insurance_provider(provider_name,contact_details) SELECT name,contact FROM seed_provider WHERE n=i RETURNING provider_id INTO j;
        v_providers:=array_append(v_providers,j);
    END LOOP;
    FOR i IN 1..45 LOOP
        INSERT INTO treatment(category_id,service_code,treatment_name,standard_price)
        SELECT v_categories[category],'MS-'||lpad(n::text,3,'0'),name,price FROM seed_treatment WHERE n=i RETURNING treatment_id INTO j;
        v_treatments:=array_append(v_treatments,j);
    END LOOP;
    FOR i IN 1..23 LOOP
        INSERT INTO specialty(specialty_name,description) SELECT name,'Consultation discipline' FROM seed_specialty WHERE n=i RETURNING specialty_id INTO j;
        v_specialties:=array_append(v_specialties,j);
    END LOOP;
    FOR i IN 1..42 LOOP
        SELECT * INTO v_name FROM seed_person WHERE n=i;
        v_username:=lower(v_name.first_name||'.'||replace(v_name.last_name,' ','')||'.'||i);
        INSERT INTO "user"(first_name,last_name,contact_details,email,username,password)
        VALUES(v_name.first_name,v_name.last_name,'07'||lpad((10000000+i)::text,8,'0'),v_username||'@example.com',v_username,crypt('password123',gen_salt('bf',12))) RETURNING user_id INTO v_user;
        IF i<=18 THEN
            v_branch:=v_branches[1+(i-1)%3];
            v_role:=CASE WHEN i=1 THEN 'admin' WHEN i<=4 THEN 'branch_manager' WHEN i<=10 THEN 'doctor' ELSE 'receptionist_cashier' END;
            INSERT INTO users_logins(user_id,user_name) VALUES(v_user,v_username) RETURNING users_logins_id INTO v_login;
            INSERT INTO staff(branch_id,users_logins_id,first_name,last_name,contact_details,email,staff_type,role)
            VALUES(v_branch,v_login,v_name.first_name,v_name.last_name,'07'||lpad((10000000+i)::text,8,'0'),v_username||'@example.com',CASE WHEN v_role='doctor' THEN 'Medical' ELSE 'Non-Medical' END,v_role) RETURNING staff_id INTO v_staff;
            v_staffs:=array_append(v_staffs,v_staff);
            IF v_role='branch_manager' THEN UPDATE branch SET manager_staff_id=v_staff WHERE branch_id=v_branch; END IF;
            IF v_role='doctor' THEN
                INSERT INTO doctor(staff_id,doctor_name,doctor_license_number) VALUES(v_staff,'Dr. '||v_name.first_name||' '||v_name.last_name,'DEMO-SL-'||lpad(i::text,4,'0')) RETURNING doctor_id INTO j;
                v_doctors:=array_append(v_doctors,j);
                INSERT INTO doctor_specialty VALUES(j,v_specialties[1+(i-5)%3]);
                -- Two fictional general physicians also practice family medicine,
                -- demonstrating the many-to-many specialty requirement.
                IF i IN (5,8) THEN INSERT INTO doctor_specialty VALUES(j,v_specialties[4]); END IF;
            END IF;
        ELSE
            INSERT INTO patient(branch_id,first_name,last_name,date_of_birth,gender,patient_type,contact_details,email,address,user_id)
            VALUES(v_branches[1+(i-19)%3],v_name.first_name,v_name.last_name,make_date(1970+(i%35),1+(i%12),1+(i%27)),CASE WHEN i%2=1 THEN 'Male' ELSE 'Female' END,CASE WHEN i<=30 THEN 'Insured' ELSE 'Self-pay' END,'07'||lpad((10000000+i)::text,8,'0'),v_username||'@example.com',(20+i)||' Temple Road, '||(SELECT name FROM seed_branch WHERE n=1+(i-19)%3),v_user) RETURNING patient_id INTO v_patient;
            v_patients:=array_append(v_patients,v_patient);
            INSERT INTO emergency_contact(patient_id,contact_name,relationship,phone) VALUES(v_patient,'Sunil '||v_name.last_name,'Parent','077'||lpad((1000000+i)::text,7,'0'));
            INSERT INTO insurance_policy(patient_id,provider_id,policy_number,start_date,end_date,status)
            VALUES(v_patient,v_providers[1+(i-19)%6],261000000+i,CURRENT_DATE-365,CASE WHEN i<=30 THEN CURRENT_DATE+365 ELSE CURRENT_DATE-30 END,CASE WHEN i<=30 THEN 'Active' ELSE 'Expired' END) RETURNING policy_id INTO v_policy;
            v_policies:=array_append(v_policies,v_policy);
        END IF;
    END LOOP;
    FOR i IN 1..24 LOOP
        -- Three visits per patient: completed, scheduled and cancelled.
        SELECT s.branch_id INTO v_branch FROM doctor d JOIN staff s USING(staff_id) WHERE d.doctor_id=v_doctors[1+(i-1)%6];
        -- Keep the registering branch: patients can attend a different branch.
        FOR j IN 1..2 LOOP
            INSERT INTO insurance_coverage(policy_id,treatment_id,coverage_percentage,maximum_amount) VALUES(v_policies[i],v_treatments[j],CASE WHEN i%3=1 THEN 100 ELSE 80 END,10000);
        END LOOP;
        v_day:=CURRENT_DATE-1-(i%14);
        INSERT INTO appointment(patient_id,doctor_id,branch_id,appointment_date,start_time,end_time,appointment_type,status,created_by,treatment_id)
        VALUES(v_patients[i],v_doctors[1+(i-1)%6],v_branch,v_day,make_time(9+(i/6),0,0),make_time(9+(i/6),30,0),CASE WHEN i%4=0 THEN 'Walk-in' ELSE 'Consultation' END,'Scheduled','Reception',v_treatments[1]) RETURNING appointment_id INTO v_appt;
        INSERT INTO appointment_treatment(appointment_id,treatment_id,quantity,unitprice) VALUES(v_appt,v_treatments[2],1,4000);
        INSERT INTO consultation_note(appointment_id,note_content,created_at) VALUES(v_appt,'Consultation completed; findings recorded and follow-up discussed.',v_day+make_time(9+(i/6),15,0));
        CALL sp_complete_appointment(v_appt);
        SELECT staff_id INTO v_staff FROM staff WHERE branch_id=v_branch AND role='receptionist_cashier' ORDER BY staff_id LIMIT 1;
        CALL sp_generate_invoice(v_appt,v_staff,v_invoice);
        UPDATE invoice SET invoice_date=v_day WHERE invoice_id=v_invoice;
        v_total:=6500;
        IF i%3<>0 THEN
            CALL sp_record_patient_payment(v_invoice,v_total/CASE WHEN i%3=1 THEN 1 ELSE 2 END,'Cash','RCPT-'||v_invoice,v_staff);
        END IF;
        IF i<=12 THEN
            INSERT INTO insurance_claim(invoice_id,policy_id,claim_date,claim_amount,approved_amount,status)
            VALUES(v_invoice,v_policies[i],v_day+1,5200,CASE WHEN i%3=1 THEN 5200 ELSE 0 END,CASE WHEN i%3=1 THEN 'Approved' WHEN i%3=2 THEN 'Pending' ELSE 'Rejected' END);
        END IF;
        SELECT min(invoice_item_id) INTO v_item FROM invoice_item WHERE invoice_id=v_invoice;
        INSERT INTO doctor_payment(doctor_id,appointment_id,invoice_item_id,date,time,doctor_payment) VALUES(v_doctors[1+(i-1)%6],v_appt,v_item,v_day+1,'16:00',1500);
        FOR j IN 1..2 LOOP
            INSERT INTO appointment(patient_id,doctor_id,branch_id,appointment_date,start_time,end_time,appointment_type,status,created_by,treatment_id)
            VALUES(v_patients[i],v_doctors[1+(i-1)%6],v_branch,CURRENT_DATE+j-1,make_time(9+(i/6),0,0),make_time(9+(i/6),30,0),'Follow-up',CASE WHEN j=1 THEN 'Scheduled' ELSE 'Cancelled' END,'Reception',v_treatments[1]) RETURNING appointment_id INTO v_appt;
            IF i=1 AND j=1 THEN
                CALL sp_reschedule_appointment(v_appt,CURRENT_DATE+14,'09:00','09:30','Reception');
            END IF;
        END LOOP;
    END LOOP;
END;
$seed$;

COMMIT;
