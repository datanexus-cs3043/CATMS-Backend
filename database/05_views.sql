-- Reporting views retain their column contracts; replacements preserve dependent queries.
CREATE OR REPLACE VIEW v_branch_daily_appointment_summary AS
SELECT b.branch_id,
       b.branch_name,
       a.appointment_date,
       COUNT(*) AS total_appointments,
       COUNT(*) FILTER (WHERE a.status = 'Scheduled') AS scheduled_count,
       COUNT(*) FILTER (WHERE a.status = 'Completed') AS completed_count,
       COUNT(*) FILTER (WHERE a.status = 'Cancelled') AS cancelled_count
FROM appointment a
JOIN branch b ON b.branch_id = a.branch_id
GROUP BY b.branch_id, b.branch_name, a.appointment_date;

CREATE OR REPLACE VIEW v_invoice_totals AS
SELECT i.invoice_id,
       i.appointment_id,
       i.invoice_date,
       COALESCE(SUM(ii.quantity * ii.unitprice), i.amount_paid + i.balance)::NUMERIC(12, 2)
           AS billed_amount,
       i.amount_paid,
       i.balance,
       i.status
FROM invoice i
LEFT JOIN invoice_item ii ON ii.invoice_id = i.invoice_id
GROUP BY i.invoice_id, i.appointment_id, i.invoice_date,
         i.amount_paid, i.balance, i.status;


CREATE OR REPLACE VIEW v_doctor_revenue AS
SELECT d.doctor_id,
       d.doctor_name,
       a.branch_id,
       COUNT(DISTINCT a.appointment_id) FILTER (WHERE i.invoice_id IS NOT NULL) AS appointment_count,
       COUNT(DISTINCT i.invoice_id) AS invoice_count,
       COALESCE(SUM(vit.billed_amount), 0)::NUMERIC(12, 2) AS billed_revenue,
       COALESCE(SUM(i.amount_paid), 0)::NUMERIC(12, 2) AS collected_revenue
FROM doctor d
LEFT JOIN appointment a ON a.doctor_id = d.doctor_id
LEFT JOIN invoice i ON i.appointment_id = a.appointment_id
LEFT JOIN v_invoice_totals vit ON vit.invoice_id = i.invoice_id
GROUP BY d.doctor_id, d.doctor_name, a.branch_id;

CREATE OR REPLACE VIEW v_outstanding_balances AS
SELECT i.invoice_id,
       a.patient_id,
       p.first_name || ' ' || p.last_name AS patient_name,
       a.branch_id,
       b.branch_name,
       i.invoice_date,
       vit.billed_amount,
       i.amount_paid,
       i.balance,
       i.status
FROM invoice i
JOIN appointment a ON a.appointment_id = i.appointment_id
JOIN patient p ON p.patient_id = a.patient_id
JOIN branch b ON b.branch_id = a.branch_id
JOIN v_invoice_totals vit ON vit.invoice_id = i.invoice_id
WHERE i.balance > 0;


CREATE OR REPLACE VIEW v_treatment_category_usage AS
SELECT tc.category_id,
       tc.category_name,
       t.treatment_id,
       t.treatment_name,
       i.invoice_date,
       a.branch_id,
       COALESCE(SUM(at.quantity), 0)::BIGINT AS usage_count,
       COALESCE(SUM(at.quantity * at.unitprice), 0)::NUMERIC(12, 2) AS treatment_revenue,
       a.appointment_date
FROM treatment_category tc
JOIN treatment t ON t.category_id = tc.category_id
JOIN appointment_treatment at ON at.treatment_id = t.treatment_id
JOIN appointment a ON a.appointment_id = at.appointment_id AND a.status = 'Completed'
LEFT JOIN invoice i ON i.appointment_id = a.appointment_id
GROUP BY tc.category_id, tc.category_name, t.treatment_id,
         t.treatment_name, i.invoice_date, a.branch_id, a.appointment_date;

CREATE OR REPLACE VIEW v_insurance_vs_out_of_pocket AS
WITH claim_totals AS (
    SELECT c.invoice_id,
           SUM(c.claim_amount)::NUMERIC(12, 2) AS insurance_claimed_amount,
           SUM(COALESCE(c.approved_amount, 0)) FILTER (WHERE c.status = 'Approved')::NUMERIC(12, 2) AS insurance_approved_amount
    FROM insurance_claim c
    GROUP BY c.invoice_id
)
SELECT i.invoice_id,
       a.patient_id,
       a.branch_id,
       i.invoice_date,
       vit.billed_amount AS invoiced_amount,
       COALESCE(ct.insurance_claimed_amount, 0)::NUMERIC(12, 2) AS insurance_claimed_amount,
       COALESCE(ct.insurance_approved_amount, 0)::NUMERIC(12, 2) AS insurance_approved_amount,
       i.amount_paid AS out_of_pocket_paid,
       i.balance AS outstanding_amount
FROM invoice i
JOIN appointment a ON a.appointment_id = i.appointment_id
JOIN v_invoice_totals vit ON vit.invoice_id = i.invoice_id
LEFT JOIN claim_totals ct ON ct.invoice_id = i.invoice_id;
