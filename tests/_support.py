"""Isolated fixtures: no application lifespan, .env file or database connection."""

import os
from collections import deque
from contextlib import asynccontextmanager
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
# Import settings from an empty directory so a developer's .env is never read.
previous_directory = Path.cwd()
with tempfile.TemporaryDirectory() as directory:
    try:
        os.chdir(directory)
        from app.core.config import settings
    finally:
        os.chdir(previous_directory)

settings.JWT_SECRET_KEY = "isolated-tests-only-jwt-key-not-for-production"
settings.CSRF_SECRET_KEY = "isolated-tests-only-csrf-key-not-for-production"
settings.DATABASE_URL = "postgresql://unused:unused@127.0.0.1:1/unused"

from app.auth.schemas import JWTPayload


def user(role="admin", branch_id=1, **fields):
    return JWTPayload(user_id=10, user_type="staff", role=role, branch_id=branch_id, **fields)


class FakeConnection:
    """Records SQL and transaction exits; never opens a database socket."""

    def __init__(self, rows=(), fail_on=None, error=None):
        self.rows = deque(rows)
        self.queries = []
        self.fail_on = fail_on
        self.error = error
        self.transaction_outcomes = []
        self.in_transaction = False

    @asynccontextmanager
    async def transaction(self):
        self.in_transaction = True
        try:
            yield
        except BaseException:
            self.transaction_outcomes.append("rollback")
            raise
        else:
            self.transaction_outcomes.append("commit")
        finally:
            self.in_transaction = False

    @asynccontextmanager
    async def cursor(self, **kwargs):
        yield self

    async def execute(self, query, params=None):
        normalized = " ".join(query.split())
        self.queries.append((normalized, params, self.in_transaction))
        if self.fail_on and self.fail_on in normalized:
            raise self.error

    async def fetchone(self):
        if not self.rows:
            raise AssertionError("Unexpected fetchone: fixture exhausted")
        return self.rows.popleft()

    async def fetchall(self):
        if not self.rows:
            raise AssertionError("Unexpected fetchall: fixture exhausted")
        return self.rows.popleft()
