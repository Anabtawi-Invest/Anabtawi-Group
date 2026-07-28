from odoo import Command

from .common import ApprovalMatrixCase


class TestAllocationConversion(ApprovalMatrixCase):
    def test_hours_stay_hours_and_direct_hours_sync(self):
        task = self._new_task(
            approval_required=False,
            allocation_value=6.5,
            allocation_unit="hours",
        )
        self.assertEqual(task.allocated_hours, 6.5)
        task.write({"allocated_hours": 9.0})
        self.assertEqual(task.allocation_unit, "hours")
        self.assertEqual(task.allocation_value, 9.0)
        self.assertEqual(task.allocated_hours, 9.0)

    def test_selected_calendar_converts_days(self):
        calendar = self.env["resource.calendar"].create(
            {
                "name": "Six Hour Calendar",
                "company_id": self.company.id,
                "hours_per_day": 6.0,
            }
        )
        task = self._new_task(
            approval_required=False,
            allocation_value=3.0,
            allocation_unit="days",
            allocation_calendar_id=calendar.id,
        )
        self.assertEqual(task.allocated_hours, 18.0)

    def test_employee_calendar_precedes_company_calendar(self):
        calendar = self.env["resource.calendar"].create(
            {
                "name": "Employee Six Hours",
                "company_id": self.company.id,
                "hours_per_day": 6.0,
            }
        )
        self.env["hr.employee"].create(
            {
                "name": "Calendar Employee",
                "user_id": self.task_user.id,
                "company_id": self.company.id,
                "resource_calendar_id": calendar.id,
            }
        )
        task = self._new_task(
            approval_required=False,
            allocation_value=2.0,
            allocation_unit="days",
            user_ids=[Command.set([self.task_user.id])],
        )
        self.assertEqual(task.allocated_hours, 12.0)

    def test_company_calendar_and_eight_hour_fallback(self):
        company_calendar = self.env["resource.calendar"].create(
            {
                "name": "Company Seven Hours",
                "company_id": self.company.id,
                "hours_per_day": 7.0,
            }
        )
        self.company.resource_calendar_id = company_calendar
        task = self._new_task(
            approval_required=False,
            allocation_value=2.0,
            allocation_unit="days",
            user_ids=[Command.clear()],
        )
        self.assertEqual(task.allocated_hours, 14.0)

        self.company.resource_calendar_id = False
        fallback = self._new_task(
            approval_required=False,
            name="Fallback",
            allocation_value=2.0,
            allocation_unit="days",
            user_ids=[Command.clear()],
        )
        self.assertEqual(fallback.allocated_hours, 16.0)

    def test_import_and_api_writes_synchronize(self):
        calendar = self.env["resource.calendar"].create(
            {
                "name": "Import Calendar",
                "company_id": self.company.id,
                "hours_per_day": 5.0,
            }
        )
        result = self.env["project.task"].load(
            [
                "name",
                "project_id/.id",
                "allocation_value",
                "allocation_unit",
                "allocation_calendar_id/.id",
            ],
            [
                [
                    "Imported Allocation",
                    str(self.project.id),
                    "3",
                    "days",
                    str(calendar.id),
                ]
            ],
        )
        self.assertFalse(result["messages"])
        task = self.env["project.task"].browse(result["ids"])
        self.assertEqual(task.allocated_hours, 15.0)
        task.write({"allocation_value": 4.0})
        self.assertEqual(task.allocated_hours, 20.0)
