# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class HrLeaveAllocationGenerateMultiWizard(models.TransientModel):
    _inherit = "hr.leave.allocation.generate.multi.wizard"

    def _apply_accrual_preview_to_generated_allocations(self, allocations):
        """Replicate single-allocation accrual simulation for generated records."""
        today = fields.Date.today()
        accrual_allocations = allocations.filtered(
            lambda a: a.allocation_type == "accrual" and a.accrual_plan_id and a.employee_id
        )
        for allocation in accrual_allocations:
            allocation.lastcall = allocation.date_from
            allocation.nextcall = False
            allocation.number_of_days_display = 0.0
            allocation.number_of_hours_display = 0.0
            allocation.number_of_days = 0.0
            allocation.already_accrued = False
            allocation.carried_over_days_expiration_date = False
            allocation.expiring_carryover_days = 0
            date_to = min(allocation.date_to, today) if allocation.date_to else False
            allocation._process_accrual_plans(date_to)

    def action_generate_allocations(self):
        self.ensure_one()
        employees = self._get_employees_from_allocation_mode()
        vals_list = self._prepare_allocation_values(employees)
        if not vals_list:
            return None

        allocations = self.env["hr.leave.allocation"].with_context(
            mail_notify_force_send=False,
            mail_activity_automation_skip=True,
        ).create(vals_list)

        self._apply_accrual_preview_to_generated_allocations(allocations)

        allocations.filtered(
            lambda c: c.validation_type not in ("no_validation", "hr")
        ).action_approve()
        if self.env.user.has_group("hr_holidays.group_hr_holidays_user"):
            allocations.filtered(lambda c: c.validation_type == "hr").action_approve()

        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Generated Allocations"),
            "views": [
                [self.env.ref("hr_holidays.hr_leave_allocation_view_tree").id, "list"],
                [self.env.ref("hr_holidays.hr_leave_allocation_view_form_manager").id, "form"],
            ],
            "view_mode": "list",
            "res_model": "hr.leave.allocation",
            "domain": [("id", "in", allocations.ids)],
            "context": {
                "active_id": False,
            },
        }
