import unittest

from _support import FakeConnection, user
from fastapi import HTTPException
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.api import api_router
from app.api.v1.endpoints import branches, doctors, patients, staff, users
from app.api.v1.endpoints._guards import check_branch_scope
from app.api.v1.endpoints.appointments import _get_note_row, _check_action_scope
from app.auth.schemas import JWTPayload
from app.auth.security import create_access_token, generate_csrf_token
from app.core.database import get_db
from app.schemas.staff import StaffCreate, StaffUpdate
from app.schemas.user import UserUpdate


class ScopeTests(unittest.IsolatedAsyncioTestCase):
    def test_doctor_cannot_manage_another_doctors_appointment(self):
        with self.assertRaises(HTTPException) as error:
            _check_action_scope(1, 2, user("doctor", 1, doctor_id=3))
        self.assertEqual(error.exception.status_code, 403)
        _check_action_scope(1, 2, user("doctor", 1, doctor_id=2))

    def test_branch_scope_fails_closed(self):
        for actor in (user("doctor", None), user("doctor", 2), JWTPayload(user_id=20, user_type="patient", role="patient", branch_id=1)):
            with self.subTest(actor=actor.role), self.assertRaises(HTTPException) as error:
                check_branch_scope(1, actor)
            self.assertEqual(error.exception.status_code, 403)
        check_branch_scope(1, user("doctor", 1))
        check_branch_scope(99, user("admin", None))

    async def test_patient_scope_checks_owner_and_staff_branch(self):
        with self.assertRaises(HTTPException):
            await patients._check_patient_access(FakeConnection([{"branch_id": 2}]), 1, user("doctor", 1))
        owner = JWTPayload(user_id=20, user_type="patient", role="patient", patient_id=1, branch_id=2)
        await patients._check_patient_access(FakeConnection([{"branch_id": 2}]), 1, owner)
        with self.assertRaises(HTTPException):
            await patients._check_patient_access(FakeConnection(), 2, owner)

    async def test_note_scope_rejects_other_branch_and_other_doctor(self):
        row = {"note_id": 1, "appointment_id": 1, "branch_id": 1, "doctor_id": 2}
        for actor in (user("branch_manager", 2), user("doctor", 1, doctor_id=3)):
            with self.subTest(role=actor.role), self.assertRaises(HTTPException) as error:
                await _get_note_row(FakeConnection([row]), 1, actor)
            self.assertEqual(error.exception.status_code, 403)
        self.assertEqual(await _get_note_row(FakeConnection([row]), 1, user("doctor", 1, doctor_id=2)), row)

    async def test_manager_cannot_escalate_using_role_or_staff_type(self):
        for values in ({"role": "admin", "staff_type": "Receptionist"}, {"role": "receptionist_cashier", "staff_type": "Administrator"}):
            payload = StaffCreate(branch_id=1, first_name="Test", last_name="User", email="test@example.invalid", **values)
            with self.subTest(values=values), self.assertRaises(HTTPException) as error:
                await staff.create_staff(payload, FakeConnection(), user("branch_manager"))
            self.assertEqual(error.exception.status_code, 403)

    async def test_manager_cannot_edit_privileged_staff_or_account_links(self):
        existing = dict(staff_id=2, branch_id=1, role="admin", staff_type="Administrator")
        with self.assertRaises(HTTPException):
            await staff.update_staff(2, StaffUpdate(first_name="Changed"), FakeConnection([existing]), user("branch_manager"))
        existing.update(role="doctor", staff_type="Doctor")
        with self.assertRaises(HTTPException):
            await staff.update_staff(2, StaffUpdate(users_logins_id=123), FakeConnection([existing]), user("branch_manager"))

    async def test_self_profile_cannot_change_identity_linking_fields(self):
        for payload in (UserUpdate(email="other@example.invalid"), UserUpdate(contact_details="other")):
            with self.assertRaises(HTTPException) as error:
                await users.update_user(10, payload, FakeConnection(), user("doctor"))
            self.assertEqual(error.exception.status_code, 403)

    async def test_doctor_appointment_query_is_branch_scoped(self):
        conn = FakeConnection([{"doctor_id": 2}, []])
        await doctors.get_doctor_appointments(2, None, conn, user("doctor", 1, doctor_id=2))
        self.assertIn("a.branch_id = %s", conn.queries[-1][0])
        self.assertEqual(conn.queries[-1][1], (2, 1))
        with self.assertRaises(HTTPException):
            await doctors.get_doctor_appointments(3, None, FakeConnection(), user("doctor", 1, doctor_id=2))

    async def test_manager_branch_list_is_scoped(self):
        conn = FakeConnection([[]])
        await branches.list_branches(conn, user("branch_manager", 1))
        self.assertIn("WHERE branch_id = %s", conn.queries[0][0])
        self.assertEqual(conn.queries[0][1], (1,))


class HTTPProtectionTests(unittest.TestCase):
    def setUp(self):
        app = FastAPI()  # Deliberately no production lifespan.
        app.include_router(api_router, prefix="/api")
        self.connection = FakeConnection()

        async def isolated_db():
            yield self.connection

        app.dependency_overrides[get_db] = isolated_db
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()

    def headers(self, actor=None, csrf=False):
        result = {"Authorization": "Bearer " + create_access_token((actor or user()).model_dump())}
        if csrf:
            result["X-CSRF-Token"] = generate_csrf_token("test")
        return result

    def test_new_routes_require_authentication(self):
        paths = ("/api/users", "/api/staff", "/api/branches", "/api/specialties", "/api/patients/1/invoices", "/api/doctors/1/appointments", "/api/notes/1")
        for path in paths:
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 401)

    def test_mutations_require_csrf_before_database_use(self):
        for path in ("/api/users/2", "/api/staff/2", "/api/branches/2", "/api/specialties/2", "/api/doctors/2", "/api/notes/2", "/api/patients/1/emergency-contacts/2"):
            with self.subTest(path=path):
                self.assertEqual(self.client.delete(path, headers=self.headers()).status_code, 403)
        self.assertEqual(self.connection.queries, [])

    def test_patient_cannot_read_branch_clinical_records(self):
        actor = JWTPayload(user_id=20, user_type="patient", role="patient", branch_id=1)
        for path in ("/api/branches/1/appointments", "/api/doctors/2/appointments", "/api/notes/1"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path, headers=self.headers(actor)).status_code, 403)

    def test_invalid_user_request_returns_422(self):
        response = self.client.post("/api/users", headers=self.headers(csrf=True), json={"username": "tester", "password": "test-password"})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(self.connection.queries, [])

    def test_valid_user_creation_returns_safe_response_and_hashes_password(self):
        row = dict(user_id=2, username="tester", first_name="Test", last_name="User", email="test@example.invalid", contact_details=None)
        self.connection.rows.extend([None, None, row])
        response = self.client.post("/api/users", headers=self.headers(csrf=True), json={**{k: row[k] for k in ("username", "first_name", "last_name", "email")}, "password": "test-password"})
        self.assertEqual(response.status_code, 201)
        self.assertNotIn("password", response.json())
        self.assertTrue(self.connection.queries[-1][1][-1].startswith("$argon2id$"))
        self.assertEqual(self.connection.transaction_outcomes, ["commit"])

    def test_successful_staff_delete_has_empty_204_response(self):
        self.connection.rows.append(dict(staff_id=2, branch_id=1, role="doctor", staff_type="Doctor"))
        response = self.client.delete("/api/staff/2", headers=self.headers(csrf=True))
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.content, b"")


if __name__ == "__main__":
    unittest.main()
