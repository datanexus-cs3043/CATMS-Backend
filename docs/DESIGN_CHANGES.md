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
