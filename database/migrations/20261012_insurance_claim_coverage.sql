-- MedSync: forward-only claim validation reconciliation, PostgreSQL 16+.
-- Apply only after the numbered schema/functions/triggers and earlier migrations.
-- It changes a function/trigger only: no deletes, backfills, receipts or balances.
-- Assumption: treatment maximum_amount applies once per policy/invoice (visit).
-- Annual benefits, insurer settlement and historical coverage versioning are not modeled.
-- Claim writers must use READ COMMITTED and pre-lock the invoice before updating
-- an existing claim row. A BEFORE UPDATE trigger cannot undo an earlier row lock.
-- Coverage writers must lock their parent policy before changing its rules, as the
-- application endpoints do. Validate real PostgreSQL concurrency before release.
BEGIN;

CREATE OR REPLACE FUNCTION fn_validate_insurance_claim()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_patient_id INTEGER;
    v_invoice_date DATE;
    v_policy insurance_policy%ROWTYPE;
    v_invoice_total NUMERIC;
    v_eligible NUMERIC;
    v_reserved NUMERIC;
    v_policy_reserved NUMERIC;
    v_requested NUMERIC;
BEGIN
    -- A blocking row lock cannot refresh a Repeatable Read transaction snapshot.
    -- Refuse unsupported isolation rather than validate stale reservations.
    IF current_setting('transaction_isolation') <> 'read committed' THEN
        RAISE EXCEPTION 'Insurance claim writes require Read Committed isolation'
            USING ERRCODE = 'feature_not_supported';
    END IF;

    IF TG_OP = 'UPDATE' THEN
        IF NEW.invoice_id IS DISTINCT FROM OLD.invoice_id
           OR NEW.policy_id IS DISTINCT FROM OLD.policy_id THEN
            RAISE EXCEPTION 'A filed claim cannot move to another invoice or policy'
                USING ERRCODE = 'check_violation';
        END IF;
    END IF;

    -- Serialize reservations and item/receipt changes on the invoice first.
    SELECT a.patient_id, i.invoice_date
      INTO v_patient_id, v_invoice_date
      FROM invoice i
      JOIN appointment a ON a.appointment_id = i.appointment_id
     WHERE i.invoice_id = NEW.invoice_id
     FOR UPDATE OF i;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Claim invoice does not exist'
            USING ERRCODE = 'foreign_key_violation';
    END IF;

    SELECT * INTO v_policy
      FROM insurance_policy
     WHERE policy_id = NEW.policy_id
     FOR SHARE;
    IF NOT FOUND OR v_policy.patient_id IS DISTINCT FROM v_patient_id THEN
        RAISE EXCEPTION 'Claim policy must belong to the patient on the invoice'
            USING ERRCODE = 'check_violation';
    END IF;

    IF NEW.status IS NULL OR NEW.status NOT IN ('Pending', 'Approved', 'Rejected')
       OR NEW.claim_amount IS NULL OR NEW.approved_amount IS NULL
       OR NEW.claim_amount::TEXT IN ('NaN', 'Infinity', '-Infinity')
       OR NEW.approved_amount::TEXT IN ('NaN', 'Infinity', '-Infinity')
       OR NEW.claim_amount < 0 OR NEW.approved_amount < 0
       OR NEW.approved_amount > NEW.claim_amount
       OR (NEW.status <> 'Approved' AND NEW.approved_amount <> 0) THEN
        RAISE EXCEPTION 'Insurance claim amounts or status are invalid'
            USING ERRCODE = 'check_violation';
    END IF;
    IF TG_OP = 'INSERT' THEN
        IF NEW.claim_amount <= 0 THEN
            RAISE EXCEPTION 'A new claim request must be positive'
                USING ERRCODE = 'check_violation';
        END IF;
    ELSIF NEW.claim_amount IS DISTINCT FROM OLD.claim_amount AND NEW.claim_amount <= 0 THEN
        RAISE EXCEPTION 'An explicitly changed claim request must be positive'
            USING ERRCODE = 'check_violation';
    END IF;

    -- Rejection releases a reservation, not money. A legacy excessive request,
    -- expired/inactive policy or subsequently edited coverage must not trap it.
    -- Preserve the recorded request; ownership and approved_amount = 0 still apply.
    IF NEW.status = 'Rejected' THEN
        RETURN NEW;
    END IF;

    IF v_policy.status <> 'Active'
       OR v_invoice_date < v_policy.start_date
       OR v_invoice_date > v_policy.end_date THEN
        RAISE EXCEPTION 'Insurance policy is not active on the invoice date'
            USING ERRCODE = 'check_violation';
    END IF;

    SELECT COALESCE(SUM(ii.quantity * ii.unitprice), i.amount_paid + i.balance)
      INTO v_invoice_total
      FROM invoice i
      LEFT JOIN invoice_item ii ON ii.invoice_id = i.invoice_id
     WHERE i.invoice_id = NEW.invoice_id
     GROUP BY i.invoice_id, i.amount_paid, i.balance;
    IF NEW.claim_amount > v_invoice_total THEN
        RAISE EXCEPTION 'Insurance claim request exceeds the billed invoice amount'
            USING ERRCODE = 'check_violation';
    END IF;
    IF EXISTS (
        SELECT 1 FROM invoice_item
         WHERE invoice_id = NEW.invoice_id
           AND (quantity IS NULL OR quantity <= 0 OR unitprice IS NULL
                OR unitprice < 0 OR unitprice::TEXT IN ('NaN', 'Infinity', '-Infinity'))
    ) THEN
        RAISE EXCEPTION 'Invalid invoice items prevent coverage calculation'
            USING ERRCODE = 'check_violation';
    END IF;

    PERFORM coverage_id FROM insurance_coverage
     WHERE policy_id = NEW.policy_id ORDER BY coverage_id FOR SHARE;
    IF EXISTS (
        SELECT treatment_id FROM insurance_coverage
         WHERE policy_id = NEW.policy_id
         GROUP BY treatment_id HAVING COUNT(*) > 1
    ) THEN
        RAISE EXCEPTION 'Duplicate treatment coverage rules must be resolved'
            USING ERRCODE = 'check_violation';
    END IF;

    IF EXISTS (
        SELECT 1 FROM insurance_coverage c
         WHERE c.policy_id = NEW.policy_id
           AND EXISTS (SELECT 1 FROM invoice_item ii
                        WHERE ii.invoice_id = NEW.invoice_id AND ii.treatment_id = c.treatment_id)
           AND (c.coverage_percentage IS NULL OR c.maximum_amount IS NULL
                OR c.coverage_percentage::TEXT IN ('NaN', 'Infinity', '-Infinity')
                OR c.maximum_amount::TEXT IN ('NaN', 'Infinity', '-Infinity')
                OR c.coverage_percentage NOT BETWEEN 0 AND 100 OR c.maximum_amount < 0)
    ) THEN
        RAISE EXCEPTION 'Invalid treatment coverage rules must be resolved'
            USING ERRCODE = 'check_violation';
    END IF;

    -- Group repeated frozen-price lines BEFORE applying each treatment's cap.
    WITH billed_treatments AS (
        SELECT treatment_id, SUM(quantity * unitprice) AS billed_amount
          FROM invoice_item WHERE invoice_id = NEW.invoice_id GROUP BY treatment_id
    )
    SELECT COALESCE(SUM(FLOOR(LEAST(b.billed_amount * c.coverage_percentage / 100,
                                  c.maximum_amount) * 100) / 100), 0)
      INTO v_eligible
      FROM billed_treatments b
      JOIN insurance_coverage c ON c.treatment_id = b.treatment_id
     WHERE c.policy_id = NEW.policy_id;

    v_requested := CASE WHEN NEW.status = 'Pending' THEN NEW.claim_amount
                        ELSE NEW.approved_amount END;
    IF v_eligible <= 0 OR v_requested > v_eligible THEN
        RAISE EXCEPTION 'Claim reservation exceeds eligible treatment coverage for the visit'
            USING ERRCODE = 'check_violation';
    END IF;

    SELECT COALESCE(SUM(CASE WHEN c.status = 'Pending' THEN c.claim_amount
                            WHEN c.status = 'Approved' THEN c.approved_amount ELSE 0 END), 0),
           COALESCE(SUM(CASE WHEN c.policy_id = NEW.policy_id THEN
                            CASE WHEN c.status = 'Pending' THEN c.claim_amount
                                 WHEN c.status = 'Approved' THEN c.approved_amount ELSE 0 END
                            ELSE 0 END), 0)
      INTO v_reserved, v_policy_reserved
      FROM insurance_claim c
     WHERE c.invoice_id = NEW.invoice_id AND c.claim_id IS DISTINCT FROM NEW.claim_id;
    IF v_policy_reserved + v_requested > v_eligible
       OR v_reserved + v_requested > v_invoice_total THEN
        RAISE EXCEPTION 'Pending and approved claims exceed policy coverage or invoice total'
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$$;

-- The old trigger omitted status: a status-only update must also be validated.
CREATE OR REPLACE TRIGGER trg_insurance_claim_validate
BEFORE INSERT OR UPDATE OF invoice_id, policy_id, claim_amount, approved_amount, status
ON insurance_claim
FOR EACH ROW EXECUTE FUNCTION fn_validate_insurance_claim();

COMMIT;
