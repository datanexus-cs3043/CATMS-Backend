# CATMS-Backend

Python FastAPI REST API backend and PostgreSQL database scripts for **MedSync / CATMS**.

## Technical Stack

- **Language & Runtime**: Python 3.11+
- **Framework**: FastAPI (`uvicorn` ASGI server)
- **Database Engine**: PostgreSQL hosted on Neon
- **Data Access**: psycopg 3 with an asynchronous connection pool (`psycopg_pool`)
- **Containerization**: Docker & Docker Compose

## Repository Structure

```text
CATMS-Backend/
├── app/             # FastAPI application
│   ├── __init__.py
│   └── main.py      # Entry point & base routes
├── database/        # Numbered SQL files (01 to 10), organized for database review and evaluation
├── compose.yaml     # Multi-container Docker Compose setup
├── Dockerfile       # Container build definition
├── requirements.txt # Python dependencies
└── .env.example     # Environment configuration template
```

## Local Development Execution

### Option 1: Local Python Environment (without docker)

1. Create and activate a virtual environment:
   ```bash
   python -m venv venv
   # On Windows:
   venv\Scripts\activate
   # On Linux/macOS:
   source venv/bin/activate
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Setup environment variables:
   ```bash
   cp .env.example .env
   ```

   Set `DATABASE_URL` to the Neon connection string, including its SSL settings, and configure the authentication secrets in your local `.env`. Do not commit credentials.

4. Run FastAPI development server with hot-reload:
   ```bash
   uvicorn app.main:app --reload --port 8000
   ```

The API will be available at `http://localhost:8000` (interactive documentation at `http://localhost:8000/docs`).

### Option 2: Docker Compose

Keep `CATMS-Frontend` beside `CATMS-Backend` in the same parent directory, and configure the backend `.env` as described above. Run this command from `CATMS-Backend`:

```bash
docker compose up --build
```

Compose runs the backend and frontend containers; the database remains hosted on Neon.

## Specialty Name Uniqueness

The API trims specialty names and compares them without case sensitivity. The
`uq_specialty_name_normalized` unique index enforces case-insensitive uniqueness
and ignores leading/trailing ordinary spaces at the database level. It does not
rewrite stored names. Fresh database setup includes it in `database/04_indexes.sql`.

For an existing database, verify the intended database/schema and review duplicate
IDs with this read-only query before any schema change:

```sql
SELECT LOWER(BTRIM(specialty_name)) AS normalized_name,
       ARRAY_AGG(specialty_id ORDER BY specialty_id) AS specialty_ids
FROM specialty
GROUP BY LOWER(BTRIM(specialty_name))
HAVING COUNT(*) > 1;
```

If duplicates exist, review their doctor assignments before deciding how to resolve
them; do not automatically delete or merge records. Once reviewed and explicitly
approved for that target, apply
`database/migrations/20261008_specialty_name_uniqueness.sql` **once**, using a SQL
client that stops on errors (for example, `psql -v ON_ERROR_STOP=1 -f <migration>`).
Do not run it if the same index was already installed by the fresh-setup script.
Do not rerun `01_database.sql` or the numbered pipeline against an existing database.

The migration uses one transaction and bounded lock/statement waits. Duplicate
names cause failure without modifying records; on an interactive-client failure,
issue `ROLLBACK` before continuing. Existing API mutation guards translate unique
violations into `409 Conflict`, including concurrent creation and rename conflicts.
Repository SQL changes are not automatically applied to Neon at application startup.

## Central Documentation

For system specifications and architecture guidelines, visit the **[project-docs Repository](https://github.com/datanexus-cs3043/project-docs)**.
