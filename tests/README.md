# PR #9 regression checks

Use an isolated Python environment with the existing backend dependencies and the HTTP test client:

```powershell
python -m pip install -r requirements.txt httpx
python -B -m unittest discover -s tests -v
```

The checks use `unittest`, real Pydantic validation and FastAPI dependencies, and a fake async database connection. They do not start the production application lifespan, load the developer's `.env`, run migrations, or contact a database. Fixtures contain only synthetic values.

- `test_pr9_validation.py`: required fields, explicit nulls, blank/oversized text, local appointment times and notes.
- `test_pr9_access.py`: branch/record scope, staff privilege management, user account-linking fields, JWT/CSRF enforcement and selected HTTP responses.
- `test_pr9_mutations.py`: transactional handler boundaries, constraint error translation, trusted attribution, rescheduling and booking checks.

The transaction fixture records commit/rollback exits; it is **not** a PostgreSQL transaction implementation. SQL execution, real foreign-key rollback, locking/concurrency, and database integration still need a disposable PostgreSQL test environment. Legacy handlers are outside this correction phase and remain unchanged.
