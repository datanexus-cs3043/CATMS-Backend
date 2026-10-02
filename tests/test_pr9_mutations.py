from datetime import date, time
import unittest

from _support import FakeConnection, user
from fastapi import HTTPException
from psycopg.errors import ForeignKeyViolation, NotNullViolation, UniqueViolation

from app.api.v1.endpoints import appointments, branches, doctors, specialties, users
from app.api.v1.endpoints._guards import database_mutation
from app.schemas.appointment import EmergencyAppointmentCreate, RescheduleRequest
from app.schemas.branch import BranchUpdate
from app.schemas.doctor import SpecialtyUpdate
from app.schemas.user import UserUpdate


def appointment_row(**changes):
    return {**dict(appointment_id=1, patient_id=1, doctor_id=2, branch_id=1,
                   appointment_date=date(2026, 10, 3), start_time=time(10), end_time=time(11),
                   appointment_type="Routine", created_by="10", treatment_id=None,
                   original_appointment_id=None), **changes}


class MutationTests(unittest.IsolatedAsyncioTestCase):
    async def test_constraint_errors_are_translated_after_rollback(self):
        for error, status in ((ForeignKeyViolation("fixture"), 409), (UniqueViolation("fixture"), 409), (NotNullViolation("fixture"), 422)):
            conn = FakeConnection()
            with self.subTest(error=type(error).__name__), self.assertRaises(HTTPException) as caught:
                async with database_mutation(conn):
                    raise error
            self.assertEqual(caught.exception.status_code, status)
            self.assertEqual(conn.transaction_outcomes, ["rollback"])

    async def test_multi_step_deletes_do_not_commit_after_later_failure(self):
        cases = (
            (users.delete_user, 'DELETE FROM "user"', {"user_id": 2}),
            (doctors.delete_doctor, "DELETE FROM doctor WHERE", {"doctor_id": 2}),
            (specialties.delete_specialty, "DELETE FROM specialty WHERE", {"specialty_id": 2}),
        )
        for handler, fail_on, row in cases:
            conn = FakeConnection([row], fail_on, ForeignKeyViolation("fixture"))
            with self.subTest(handler=handler.__name__), self.assertRaises(HTTPException) as caught:
                await handler(2, conn, user())
            self.assertEqual(caught.exception.status_code, 409)
            self.assertEqual(conn.transaction_outcomes, ["rollback"])
            deletes = [query for query in conn.queries if query[0].startswith("DELETE")]
            self.assertEqual(len(deletes), 2)
            self.assertTrue(all(query[2] for query in deletes))

    async def test_user_self_deletion_is_rejected(self):
        conn = FakeConnection()
        with self.assertRaises(HTTPException):
            await users.delete_user(10, conn, user())
        self.assertEqual(conn.queries, [])

    async def test_nullable_user_contact_details_are_written_as_null(self):
        row = dict(user_id=2, username="tester", first_name="Test", last_name="User", email="test@example.invalid", contact_details=None)
        conn = FakeConnection([{"user_id": 2}, row])
        await users.update_user(2, UserUpdate(contact_details=None), conn, user())
        self.assertIn("contact_details = %s", conn.queries[-1][0])
        self.assertEqual(conn.queries[-1][1], (None, 2))

    async def test_specialty_update_checks_duplicate_name(self):
        conn = FakeConnection([{"specialty_id": 1}, {"specialty_id": 2}])
        with self.assertRaises(HTTPException) as caught:
            await specialties.update_specialty(1, SpecialtyUpdate(specialty_name=" Existing "), conn, user())
        self.assertEqual(caught.exception.status_code, 409)
        self.assertEqual(conn.transaction_outcomes, ["rollback"])
        self.assertFalse(any(q[0].startswith("UPDATE") for q in conn.queries))

    async def test_branch_manager_assignment_requires_same_branch(self):
        conn = FakeConnection([{"branch_id": 1}, None])
        with self.assertRaises(HTTPException) as caught:
            await branches.update_branch(1, BranchUpdate(manager_staff_id=5), conn, user())
        self.assertEqual(caught.exception.status_code, 422)
        self.assertEqual(conn.queries[-1][1], (5, 1))

    async def test_reschedule_records_authenticated_creator_and_preserves_link(self):
        result = appointment_row(appointment_id=3, original_appointment_id=1)
        conn = FakeConnection([appointment_row(), None, {"branch_id": 1}, None, result])
        payload = RescheduleRequest(appointment_date="2026-10-03", start_time="11:00", end_time="12:00", created_by="spoofed")
        await appointments.reschedule_appointment(1, payload, conn, user())
        query, params, in_transaction = conn.queries[-1]
        self.assertTrue(in_transaction)
        self.assertEqual(params[7:9], ("10", 1))
        self.assertIn("FOR UPDATE", conn.queries[0][0])
        self.assertEqual(conn.transaction_outcomes, ["commit"])

    async def test_duplicate_reschedule_is_rejected(self):
        conn = FakeConnection([appointment_row(), {"appointment_id": 3}])
        payload = RescheduleRequest(appointment_date="2026-10-03", start_time="11:00", end_time="12:00")
        with self.assertRaises(HTTPException) as caught:
            await appointments.reschedule_appointment(1, payload, conn, user())
        self.assertEqual(caught.exception.status_code, 409)
        self.assertFalse(any(q[0].startswith("INSERT") for q in conn.queries))

    async def test_emergency_creator_is_not_caller_supplied(self):
        result = appointment_row(appointment_type="Emergency")
        conn = FakeConnection([{"patient_id": 1}, {"doctor_id": 2}, {"branch_id": 1}, {"branch_id": 1}, None, result])
        payload = EmergencyAppointmentCreate(patient_id=1, doctor_id=2, branch_id=1,
                                            appointment_date="2026-10-03", start_time="10:00", end_time="11:00", created_by="spoofed")
        await appointments.create_emergency_appointment(payload, conn, user())
        self.assertEqual(conn.queries[-1][1][-2], "10")

    async def test_booking_rejects_wrong_branch_and_overlap(self):
        for rows, expected in (([{"branch_id": 2}], 422), ([{"branch_id": 1}, {"appointment_id": 9}], 409)):
            conn = FakeConnection(rows)
            with self.subTest(expected=expected), self.assertRaises(HTTPException) as caught:
                await appointments._check_booking(conn, 2, 1, date(2026, 10, 3), time(10), time(11))
            self.assertEqual(caught.exception.status_code, expected)

    async def test_complete_and_cancel_remain_explicit_stubs(self):
        for handler in (appointments.complete_appointment, appointments.cancel_appointment):
            conn = FakeConnection([appointment_row()])
            with self.subTest(handler=handler.__name__), self.assertRaises(HTTPException) as caught:
                await handler(1, conn, user())
            self.assertEqual(caught.exception.status_code, 501)
            self.assertFalse(any(q[0].startswith(("INSERT", "UPDATE", "DELETE")) for q in conn.queries))


if __name__ == "__main__":
    unittest.main()
