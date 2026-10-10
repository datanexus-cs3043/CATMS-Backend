# CATMS design changes (simple words)

This file explains each change we make to finish CATMS against the project brief:
what was wrong, what we changed, and whether the Neon database needs an update.
Newest changes go at the bottom.

## How the pieces fit

- **Database (PostgreSQL on Neon)**: the numbered files in `database/` build it.
  `02_tables.sql` has the 20 base tables; `05`–`08` add appointment status, the
  `appointment_treatment` and `patient_payment` tables, report views, functions,
  procedures and triggers. Triggers keep invoice totals correct automatically.
- **Backend (FastAPI)**: `app/api/v1/endpoints/` turns HTTP requests into SQL and
  checks who is allowed to do what (role, branch, own records).
- **Frontend (React)**: pages call the backend through `src/services/api.ts`.

When a change needs new SQL, it is added to the right numbered file **and** to a
file in `database/migrations/`. That migration file must be run once in Neon.

## Sithuka's contributions (from Git history)

Taken from `git log` of all three repositories. Commits that appear twice (the same
change on two branches) are counted once. Dates are commit dates.

### Backend and database (CATMS-Backend)
- **Sep 14 – database setup.** Started `01_database.sql` (database creation plus
  `DROP TABLE` statements so the schema can be rebuilt from scratch).
- **Sep 15 – first tables.** Wrote `user`, `branch`, `users_logins` and `staff` in
  `02_tables.sql`: logins, the clinic branches and the staff who work in them.
- **Sep 14 / Sep 23 – Docker.** Turned the frontend service in `compose.yaml` off
  while the frontend was not ready, then back on.
- **Oct 7 – appointment status (`05_views.sql`).** Added `appointment.status` with a
  check that only allows Scheduled, Completed or Cancelled (brief requirement).
- **Oct 7 – `appointment_treatment` table.** Lets one appointment have several
  treatments with quantity and the price at that time (brief: "one or more
  treatments"). Indexes for fast lookup by appointment and treatment.
- **Oct 7 – `patient_payment` table.** A ledger of what patients pay (full or
  partial), separate from doctor pay, so outstanding dues can be tracked.
- **Oct 7 – report views.** `v_branch_daily_appointment_summary`, `v_doctor_revenue`,
  `v_outstanding_balances`, `v_treatment_category_usage` and
  `v_insurance_vs_out_of_pocket`: one view per report in the brief.
- **Oct 7 – functions and triggers (`06_functions.sql`).**
  - `fn_recalculate_invoice`: total = sum of invoice items; paid = sum of patient
    payments; sets balance and Paid / Partially Paid / Unpaid automatically.
  - Invoice item and payment triggers that lock the invoice row and recalculate it,
    so two cashiers cannot corrupt a total at the same time (ACID).
  - `fn_prepare_invoice` / `fn_sync_invoice_payment_ledger`: keep the invoice and
    the payment ledger consistent when either side changes.
  - `fn_validate_appointment`: end time after start time, no reopening of completed
    or cancelled visits, and a rescheduled visit keeps the same patient, doctor and
    branch. `fn_sync_appointment_treatment` keeps the booked service in the
    treatment list. (Doctor double-booking is blocked by the exclusion constraint
    in `08_triggers.sql`.)
  - `fn_validate_insurance_claim`: a claim must use the patient's own active policy
    and cannot be more than the invoice; `fn_validate_doctor_payment` checks doctor
    payments belong to that doctor's appointment.
- **Oct 7 – SQL smoke tests (`10_tests.sql`).** Checks that the status rule,
  treatment links and invoice totals behave as expected.
- **Oct 10 – API fixes.** Receptionist branch access, several treatments per
  appointment, doctors seeing patients from any branch, `sp_generate_invoice`
  (details in the numbered changes below).

### Frontend (CATMS-Frontend)
- **Aug 30 – Sep 23 – project start.** First upload, the Vite + React project setup,
  README with Docker commands, Nginx configuration for the container.
- **Oct 2 – personal pages.** My Bills, My Patients, My Profile and My Appointments
  pages for patients and doctors.
- **Oct 3 – login.** Authentication context with logout and role handling; image
  assets for the UI.
- **Oct 4 – main pages.** Appointments, Appointment Details, Branches, Dashboard,
  Doctors and Doctor Details pages with loading/error states and filters; styling
  of the appointment form, data table and payment form.
- **Oct 6 – Tailwind.** Moved the styles to Tailwind CSS and reorganised the API
  service.
- **Oct 7 – role routes.** Role-specific routes in `App.tsx`.
- **Oct 10 – fixes.** CSRF on every save, restoring teammates' work lost in a merge,
  insurance routes, recording treatments before completion, dashboard branch call.

### Shared docs (project-docs)
- **Oct 10** – updated `implementation_status.md` and `roles_and_reports.md` to match
  the code (complete/cancel implemented, appointment treatments contract).

## Changes so far

### 1. CSRF token on every save (frontend)
- **Problem:** the backend rejects any POST/PUT/DELETE without an `X-CSRF-Token`
  header, but the frontend only sent it for staff and doctor updates.
- **Change:** `api.ts` fetches the token once from `/auth/csrf`, adds it to every
  save request, clears it on login/logout and retries once if it expired.
- **Neon:** no change.

### 2. Receptionist can load their branch (backend)
- **Problem:** `GET /branches` allowed only admin and branch manager, so the
  receptionist's Dashboard, Appointments and Patients pages failed with 403.
- **Change:** `receptionist_cashier` may call it too; non-admins still see only
  their own branch.
- **Neon:** no change.

### 3. Insurance pages use the real backend routes (frontend)
- **Problem:** the frontend called `/insurance-providers`, `/insurance-policies`,
  `/insurance-claims` and `/patients/{id}/insurance-policies`, which do not exist.
- **Change:** calls now use `/insurance/providers|policies|coverage|claims` and
  `/patients/{id}/insurance`. Only admins see "Add Provider" (backend rule).
- **Neon:** no change.

### 4. Consultation notes are clinical (frontend)
- Receptionists and patients no longer request or see consultation notes; the
  backend only serves them to admin, branch manager and doctors.

### 5. Several treatments per appointment (backend + frontend)
- **Problem:** the brief says doctors may prescribe one or more treatments, but the
  API stored a single `appointment.treatment_id`.
- **Change:** `/appointments/{id}/treatments` now reads and writes the
  `appointment_treatment` table: several treatments, each with a quantity and the
  catalogue price copied at that moment (so later price changes do not change old
  bills). Treatments are locked once the appointment is cancelled or invoiced.
  Treatments can be recorded before marking the visit Completed, because
  `sp_complete_appointment` only completes visits that have a treatment or note.
- **Neon:** needs the `appointment_treatment` table from `05_views.sql` and the
  sync trigger from `06`/`08`.

### 6. Doctors see their patients from any branch (backend)
- **Problem:** the brief says patient records are shared across branches, but a
  doctor could not open a patient registered at another branch.
- **Change:** doctors may see any patient they have an appointment with.
- **Neon:** no change.

### 7. Invoice built from the recorded treatments (database)
- **Problem:** creating an invoice only inserted an empty header, so the bill had
  no lines and a total of 0. The brief says invoices come from completed treatments.
- **Change:** new procedure `sp_generate_invoice(appointment, staff)` in
  `07_procedures.sql`. In one transaction it checks the visit is Completed, not
  already billed, has treatments, and the staff member works at that branch; then
  it creates the invoice and copies every treatment into `invoice_item`. Existing
  triggers set the total, balance and status.
- **Neon:** run `database/migrations/20261010_generate_invoice.sql` once.
