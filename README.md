# CATMS-Backend

Python FastAPI REST API and PostgreSQL database scripts for **MedSync / CATMS**, a Clinic Appointment and Treatment Management System developed for CS3043 by DataNexus.

[Web application](https://www.medsync.live) · [Primary API](https://backend.medsync.live/api/health) · [API documentation](https://backend.medsync.live/docs) · [Frontend repository](https://github.com/datanexus-cs3043/CATMS-Frontend) · [Project documentation](https://github.com/datanexus-cs3043/project-docs)

## Team Contributions

Work was collaborative across the frontend, backend and database. The following summarizes each member's contribution areas; these are shared areas of work, not exclusive ownership of entire modules.

| Member | Contribution areas |
| --- | --- |
| Shashika | Pydantic request/response schemas and validation; backend foundation and patient/doctor/appointment integration; cross-layer integration corrections; Docker, CI/CD, deployment, hosting and project documentation |
| Nayanajith Bandara | Authentication, authorization and security; account/role integration and backend API structure; staff, branch and treatment APIs; billing/insurance/report API integration and stored procedures |
| Tharushi | Frontend foundation and shared components; patient, staff, treatment and profile interfaces; appointment lifecycle endpoints; insurance, consultation, claim and payment table contributions |
| Adithya | Invoice, insurance, branch-management and patient-facing interfaces; report presentation; database procedures, integrity constraints and appointment/treatment/billing/insurance triggers |
| Sithuka | Account/branch/staff SQL and appointment status/treatment bridge; invoice-generation routine and patient-receipt ledger; report views and functions; dashboard and frontend API/CSRF integration |

## Functional Overview

- Patient records, emergency contacts and optional patient portal accounts; shared patient access across clinics with scoped writes.
- Branch, staff, doctor, specialty and treatment catalogue management. Doctors belong to one branch and can have multiple specialties.
- Staff-managed appointment booking, rescheduling, cancellation and completion; doctor consultation notes and multiple recorded treatments with captured quantities and prices.
- Invoice generation from completed visits, issued invoice items, partial patient receipts and separate doctor compensation records.
- Insurance providers, patient policies, treatment coverage and pending/approved/rejected claims.
- Five management reports: daily branch appointments, doctor revenue, outstanding patient balances, treatments by category, and insurance versus out-of-pocket payments.

| Role | Main access |
| --- | --- |
| Admin | System-wide administration, accounts, clinical/financial administration and reports |
| Branch manager | Assigned-branch operations, billing and reports, with shared patient reads |
| Receptionist/cashier | Patient administration, staff-managed scheduling, billing and insurance within authorized scope |
| Doctor | Own appointments and related patients, consultation notes, treatments and own compensation |
| Patient | Own appointments, bills, receipts and insurance information, plus permitted profile updates |

Authentication, role, branch and patient-ownership checks are enforced by the API. Patient portal access does not provide self-service scheduling.

Cancellation and rescheduling call PostgreSQL `sp_cancel_appointment` and `sp_reschedule_appointment` within guarded transactions. Rescheduling retains the original visit and links a successor appointment rather than overwriting its history.

### Financial and Report Definitions

`patient_payment` is the signed patient receipt/refund/adjustment ledger; `doctor_payment` records doctor compensation. An Approved insurance claim is a coverage decision, **not cash received**, and does not automatically reduce invoice balance. Coverage percentages and caps apply per policy/invoice; annual benefits and insurer settlement accounting are not modeled.

Appointment summaries and treatment usage filter visit dates; revenue, outstanding and insurance reports filter invoice dates. Financial reports show current values for that invoice cohort, not historical balances reconstructed at the end date. The frontend offers browser Print / Save as PDF; the API returns report data rather than server-generated PDFs.

## Technical Stack

- Python 3.11+, FastAPI, Uvicorn and Pydantic.
- PostgreSQL hosted externally on Neon; direct parameterized SQL through **psycopg 3** and `psycopg_pool`, without an ORM.
- SQL constraints, indexes, views, functions, procedures and triggers for integrity and derived totals.
- Argon2id password hashing, legacy bcrypt verification, JWT/HttpOnly cookies and account-bound CSRF validation.
- Docker/Compose, GitHub Actions and Azure App Service.

## Repository Structure

```text
app/
  main.py           # Application lifecycle, CORS and API mounting
  api/v1/endpoints/ # Domain routes and SQL access
  auth/             # Authentication, authorization and CSRF
  core/             # Configuration and asynchronous connection pool
  schemas/          # Request/response validation
database/           # Fresh-schema SQL 01–10, migrations and seed documentation
scripts/            # Deployment/database verification helpers
.github/workflows/  # Azure deployment and database validation workflows
compose.yaml        # Backend + sibling frontend; no database container
run.py              # Local development entry point, including Windows loop setup
```

## Local Development Execution

Prerequisites: Python 3.11+, an accessible PostgreSQL database with the required schema, and its connection details. Run commands from this repository. Use an isolated development database for setup and demonstration data.

**Windows PowerShell**

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

**Linux/macOS**

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

Edit the local `.env` before starting:

| Setting | Local configuration |
| --- | --- |
| `DATABASE_URL` | Your PostgreSQL/Neon connection string with the required TLS settings |
| `JWT_SECRET_KEY`, `CSRF_SECRET_KEY` | Independently generated, distinct private values; use at least 32 characters each |
| `FRONTEND_URLS` | Exact allowed origins, e.g. `http://localhost:5173` (no URL path) |
| `ENVIRONMENT` | `development` locally; explicitly `production` when hosted |
| `COOKIE_SECURE`, `COOKIE_SAMESITE` | `false`, `lax` for local HTTP; secure cookies for hosted HTTPS |
| `PORT` | `8000` by default |

Keep connection strings and secrets outside Git and frontend variables. Production validation rejects source-default/short/equal authentication secrets and insecure cookies; `SameSite=None` also requires `COOKIE_SECURE=true`.

Start the development server after configuration:

```bash
python run.py
```

Local endpoints: [API health](http://localhost:8000/api/health), [Swagger UI](http://localhost:8000/docs), [ReDoc](http://localhost:8000/redoc), and [OpenAPI](http://localhost:8000/api/openapi.json).

### Docker Compose

Place `CATMS-Frontend` beside `CATMS-Backend`, configure the backend `.env`, and run from this repository:

```bash
docker compose up --build
```

The backend uses port 8000 by default and the frontend uses port 5173. PostgreSQL remains external; Compose does not initialize Neon. The frontend Docker build defaults to `http://localhost:8000/api`; its API address is a **build-time** Vite setting. For another target, pass `--build-arg VITE_API_BASE_URL=https://backend.medsync.live/api` when building the frontend image, or supply the equivalent frontend build argument in your Compose configuration. See the [frontend Docker instructions](https://github.com/datanexus-cs3043/CATMS-Frontend#docker-container).

## Database Setup and Migrations

For a **fresh empty application schema only**, review and run SQL files 01–08 in numeric order. Before seed file 09, install PostgreSQL `pgcrypto` (`CREATE EXTENSION IF NOT EXISTS pgcrypto;`) using an account permitted to create it. Then run 09 for optional demonstration data and 10 for SQL assertions, with a client configured to stop on errors. The seed refuses a populated target. See [Sri Lankan demonstration data](database/SEED_DATA.md) for prerequisites and fictional-data boundaries.

For an existing database, inspect its installed objects and use reviewed, target-specific [forward migrations](database/migrations/). Do not replay the numbered schema/seed pipeline or blindly apply every historical migration. Application startup and repository pushes do not automatically apply live migrations.

Specialty uniqueness uses `LOWER(BTRIM(specialty_name))` through `uq_specialty_name_normalized`. Before applying the [existing-database migration](database/migrations/20261008_specialty_name_uniqueness.sql), check whether that index is already installed and resolve duplicate names and doctor links through review; do not automatically delete or merge records.

## Hosting and CI/CD

The primary frontend is [www.medsync.live](https://www.medsync.live) on Vercel; the primary backend is [backend.medsync.live](https://backend.medsync.live) on Azure App Service. [Render](https://catms-backend-fa6t.onrender.com/api/health) is a backend standby, not automatic failover. A URL does not establish identical deployed revisions or sessions across hosts.

- [Azure deployment](.github/workflows/main_catms-backedn.yml) runs on main pushes affecting `app/**`, `requirements.txt` or `run.py`, or manual dispatch. Releases are serialized without cancelling the active run; documentation/database-only pushes do not trigger this deployment.
- [Neon validation](.github/workflows/neon-sync.yml) checks fresh SQL and the selected integrity migration on disposable PostgreSQL 16. A manual main run then performs a protected, **read-only** live Neon check. It does not apply live migrations or guarantee all application tests pass.

Verify the intended backend/frontend revisions, installed database objects, role-scoped workflows and report output in the target environment before release. Build or health success alone is not full workflow verification.

## Central Documentation

See the [project-docs repository](https://github.com/datanexus-cs3043/project-docs) for system requirements, architecture, roles, reports and database design, and the [frontend repository](https://github.com/datanexus-cs3043/CATMS-Frontend) for client setup.
