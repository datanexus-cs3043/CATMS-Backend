-- Extensions required to retain appointment states and treatment/payment detail
-- without changing the API's existing table/column contract.
DROP VIEW IF EXISTS v_insurance_vs_out_of_pocket;
DROP VIEW IF EXISTS v_invoice_financial_summary;
DROP VIEW IF EXISTS v_treatment_category_usage;
DROP VIEW IF EXISTS v_outstanding_balances;
DROP VIEW IF EXISTS v_doctor_revenue;
DROP VIEW IF EXISTS v_invoice_totals;
DROP VIEW IF EXISTS v_branch_daily_appointment_summary;

ALTER TABLE appointment
    ADD COLUMN IF NOT EXISTS status VARCHAR(20) NOT NULL DEFAULT 'Scheduled';
