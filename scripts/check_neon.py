"""Check the shared Neon schema without changing records, routines or migration history."""
import hashlib
import os
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit

import psycopg


def validate_target(url):
    target = urlsplit(url)
    if target.scheme not in {"postgres", "postgresql"} or not (target.hostname or "").endswith(".neon.tech"):
        raise ValueError("NEON_DATABASE_URL must point to the approved Neon database")
    expected = os.environ.get("NEON_DATABASE_NAME", "neondb")
    if unquote(target.path.lstrip("/")) != expected:
        raise ValueError("NEON_DATABASE_URL names a different database than NEON_DATABASE_NAME")
    return expected


def check(url):
    expected = validate_target(url)
    source = Path("database/02_tables.sql").read_text(encoding="utf-8-sig")
    required_tables = set(re.findall(r'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?("?\w+"?)\s*\(', source, re.IGNORECASE))
    required_tables = {name.strip('"') for name in required_tables}
    if len(required_tables) != 22:
        raise RuntimeError("Review the expected schema before changing the Neon validation baseline")

    # Pooled Neon connections reject some startup options; set them in a read-only transaction.
    with psycopg.connect(url, connect_timeout=15) as conn:
        with conn.cursor() as cur:
            cur.execute("SET TRANSACTION READ ONLY")
            cur.execute("SET LOCAL statement_timeout = '15s'")
            cur.execute("SELECT current_database(), current_setting('transaction_read_only')")
            database, read_only = cur.fetchone()
            if database != expected or read_only != "on":
                raise RuntimeError("Database target/read-only verification failed")
            cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE'")
            missing = required_tables - {row[0] for row in cur.fetchall()}
            if missing:
                raise RuntimeError("Missing required tables: " + ", ".join(sorted(missing)))
            cur.execute("SELECT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='ex_appointment_doctor_time' AND conrelid=to_regclass('public.appointment'))")
            if not cur.fetchone()[0]:
                raise RuntimeError("Doctor appointment overlap constraint is missing")
            cur.execute("SELECT to_regprocedure('public.sp_generate_invoice(integer,integer,integer)') IS NOT NULL")
            if not cur.fetchone()[0]:
                raise RuntimeError("Invoice generation procedure is missing")
            cur.execute("SELECT tgname FROM pg_trigger WHERE NOT tgisinternal AND tgrelid IN (to_regclass('public.branch'),to_regclass('public.staff'))")
            triggers = {row[0] for row in cur.fetchall()}
            if not {"trg_branch_manager_validate", "trg_staff_assignment_validate"}.issubset(triggers):
                print("::warning::Original-brief integrity guards are not fully installed. Review 20261012_original_brief_integrity.sql before a separately authorized application.")
            cur.execute("SELECT to_regclass('public.schema_migrations') IS NOT NULL")
            if cur.fetchone()[0]:
                cur.execute("SELECT filename, checksum FROM public.schema_migrations")
                history = dict(cur.fetchall())
                for path in sorted(Path("database/migrations").glob("*.sql")):
                    recorded = history.get(path.name)
                    checksum = hashlib.sha256(path.read_bytes()).hexdigest()
                    if recorded is None:
                        print("::warning::No migration-history entry for " + path.name + "; inspect existing objects before applying it.")
                    elif recorded != checksum:
                        raise RuntimeError("Applied migration checksum differs: " + path.name + "; add a new forward migration instead of replaying it")
            else:
                print("::warning::No migration ledger exists. Existing routines may have been applied manually; historical migrations were not replayed.")
    print("Neon connectivity and required schema checks passed; transaction was read-only and no SQL changes were applied.")


if __name__ == "__main__":
    url = os.environ.get("NEON_DATABASE_URL", "")
    if not url:
        raise SystemExit("NEON_DATABASE_URL is missing from the neon environment secrets")
    try:
        check(url)
    except (ValueError, RuntimeError) as exc:
        raise SystemExit(str(exc)) from None
    except Exception as exc:
        # Connection exceptions can contain the DSN; never echo them into Actions logs.
        raise SystemExit("Neon validation failed (" + type(exc).__name__ + "). Check the environment secret, network and database availability.") from None
