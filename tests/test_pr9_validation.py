import unittest

import _support
from pydantic import ValidationError

from app.schemas.appointment import ConsultationNoteUpdate, EmergencyAppointmentCreate, RescheduleRequest
from app.schemas.branch import BranchCreate, BranchUpdate
from app.schemas.patient import EmergencyContactUpdate
from app.schemas.staff import StaffCreate, StaffUpdate
from app.schemas.user import UserCreate, UserUpdate


class RequestValidationTests(unittest.TestCase):
    def test_user_create_requires_database_required_fields(self):
        values = dict(username="tester", password="test-password")
        for missing in ("first_name", "last_name", "email"):
            with self.subTest(missing=missing), self.assertRaises(ValidationError):
                UserCreate(**{**values, **{k: "Example" for k in ("first_name", "last_name", "email") if k != missing}})

    def test_user_create_trims_before_length_validation(self):
        for username in ("   ", " a "):
            with self.subTest(username=username), self.assertRaises(ValidationError):
                UserCreate(username=username, password="test-password", first_name="Test", last_name="User", email="test@example.invalid")

    def test_update_omission_differs_from_explicit_null(self):
        models = {
            UserUpdate: ("first_name", "last_name", "email", "password"),
            BranchUpdate: ("branch_name", "location"),
            StaffUpdate: ("branch_id", "first_name", "last_name", "email", "staff_type", "role"),
            EmergencyContactUpdate: ("contact_name", "relationship", "phone"),
        }
        for model, fields in models.items():
            self.assertEqual(model().model_dump(exclude_unset=True), {})
            for field in fields:
                with self.subTest(model=model.__name__, field=field), self.assertRaises(ValidationError):
                    model(**{field: None})

    def test_nullable_fields_can_be_cleared(self):
        self.assertEqual(UserUpdate(contact_details=None).model_dump(exclude_unset=True), {"contact_details": None})
        self.assertEqual(BranchUpdate(manager_staff_id=None).model_dump(exclude_unset=True), {"manager_staff_id": None})
        self.assertEqual(StaffUpdate(users_logins_id=None).model_dump(exclude_unset=True), {"users_logins_id": None})

    def test_blank_and_oversized_branch_and_staff_input(self):
        for field in ("branch_name", "location"):
            with self.subTest(field=field), self.assertRaises(ValidationError):
                BranchCreate(**{**dict(branch_name="Clinic", location="City"), field: "   "})
        with self.assertRaises(ValidationError):
            BranchUpdate(branch_name="x" * 151)
        with self.assertRaises(ValidationError):
            StaffCreate(branch_id=1, first_name=" ", last_name="User", email="test@example.invalid", staff_type="Doctor", role="doctor")

    def test_new_appointment_actions_require_ordered_local_times(self):
        for model in (RescheduleRequest, EmergencyAppointmentCreate):
            extra = dict(patient_id=1, doctor_id=2, branch_id=1) if model is EmergencyAppointmentCreate else {}
            for start, end in (("10:00", "09:00"), ("10:00", "10:00"), ("10:00Z", "11:00Z")):
                with self.subTest(model=model.__name__, times=(start, end)), self.assertRaises(ValidationError):
                    model(appointment_date="2026-10-03", start_time=start, end_time=end, **extra)
            payload = model(appointment_date="2026-10-03", start_time="10:00", end_time="11:00", **extra)
            self.assertIsNone(payload.created_by)

    def test_blank_note_is_rejected(self):
        with self.assertRaises(ValidationError):
            ConsultationNoteUpdate(note_content="   ")


if __name__ == "__main__":
    unittest.main()
