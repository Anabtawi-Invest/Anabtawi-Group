# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError

class LatenessPreviewWizard(models.TransientModel):
    _name = "lateness.preview.wizard"
    _description = "Preview Lateness Reconciliation"

    payrun_id = fields.Many2one("hr.payslip.run", required=True, readonly=True)
    preview_results = fields.Text("Preview Results", readonly=True)

    def _get_leave_balance_hours(self, leave_type, employee):
        data = leave_type.get_days(employee.id)
        info = (data or {}).get(leave_type.id, {}) or {}
        return float(info.get("remaining_leaves", 0.0) or 0.0)

    def _update_unpaid_input(self, slip, input_code, hours):
        input_line = slip.input_line_ids.filtered(lambda l: l.input_type_id.code == input_code)[:1]
        if input_line:
            input_line.amount = hours
        else:
            it = self.env["hr.payslip.input.type"].search([("code", "=", input_code)], limit=1)
            if not it:
                raise UserError(_("Payroll Input Type not found: %s") % input_code)
            self.env["hr.payslip.input"].create({
                "payslip_id": slip.id,
                "input_type_id": it.id,
                "amount": hours,
                "name": it.name,
            })

    def _upsert_negative_allocation(self, slip, leave_type, hours, field_name, label):
        alloc = getattr(slip, field_name, False)
        if hours <= 0:
            if alloc:
                alloc.sudo().write({"number_of_days": 0.0})
            return
        vals = {
            "name": "%s - %s (%s)" % (label, slip.number or slip.name or "Payslip", slip.date_to),
            "holiday_status_id": leave_type.id,
            "employee_id": slip.employee_id.id,
            "number_of_days": -hours,
            "notes": "Auto reconciliation from Pay Run: %s" % (slip.payslip_run_id.name or ""),
        }
        if alloc:
            alloc.sudo().write(vals)
            if alloc.state not in ("validate", "validated"):
                alloc.sudo().action_approve()
        else:
            alloc = self.env["hr.leave.allocation"].sudo().create(vals)
            alloc.sudo().action_approve()
            slip.sudo().write({field_name: alloc.id})

    def action_preview(self):
        self.ensure_one()
        ot_type = self.env["hr.leave.type"].search([("name", "=", "Overtime Bank")], limit=1)
        al_type = self.env["hr.leave.type"].search([("name", "=", "Annual Leave")], limit=1)
        if not ot_type or not al_type:
            raise UserError(_("Missing time off types: Overtime Bank or Annual Leave."))

        preview_lines = []
        for slip in self.payrun_id.slip_ids:
            employee = slip.employee_id
            if not employee:
                continue
            late_entries = self.env["hr.work.entry"].search([
                ("employee_id", "=", employee.id),
                ("date_start", "<", slip.date_to),
                ("date_stop", ">", slip.date_from),
                ("work_entry_type_id.code", "=", "LATE"),
                ("state", "in", ["draft", "validated"]),
            ])
            late_hours = sum(late_entries.mapped("duration")) if late_entries else 0.0
            if late_hours <= 0:
                continue
            ot_balance = self._get_leave_balance_hours(ot_type, employee)
            al_balance = self._get_leave_balance_hours(al_type, employee)
            ot_used = min(late_hours, max(ot_balance, 0.0))
            remaining = late_hours - ot_used
            al_used = min(remaining, max(al_balance, 0.0))
            unpaid_hours = max(remaining - al_used, 0.0)

            preview_lines.append("%s: Late=%.2f h → OT=%.2f, AL=%.2f, Unpaid=%.2f" % (
                employee.name, late_hours, ot_used, al_used, unpaid_hours
            ))

        self.preview_results = "\n".join(preview_lines) or _("No lateness found.")
        return {
            "type": "ir.actions.act_window",
            "res_model": "lateness.preview.wizard",
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }

    def action_apply(self):
        self.ensure_one()
        ot_type = self.env["hr.leave.type"].search([("name", "=", "Overtime Bank")], limit=1)
        al_type = self.env["hr.leave.type"].search([("name", "=", "Annual Leave")], limit=1)
        for slip in self.payrun_id.slip_ids:
            employee = slip.employee_id
            if not employee:
                continue
            late_entries = self.env["hr.work.entry"].search([
                ("employee_id", "=", employee.id),
                ("date_start", "<", slip.date_to),
                ("date_stop", ">", slip.date_from),
                ("work_entry_type_id.code", "=", "LATE"),
                ("state", "in", ["draft", "validated"]),
            ])
            late_hours = sum(late_entries.mapped("duration")) if late_entries else 0.0
            if late_hours <= 0:
                self._update_unpaid_input(slip, "LATE_UNPAID_H", 0.0)
                slip.write({
                    "late_reco_late_hours": 0.0,
                    "late_reco_ot_hours": 0.0,
                    "late_reco_al_hours": 0.0,
                    "late_reco_unpaid_hours": 0.0,
                })
                continue
            ot_balance = self._get_leave_balance_hours(ot_type, employee)
            al_balance = self._get_leave_balance_hours(al_type, employee)
            ot_used = min(late_hours, max(ot_balance, 0.0))
            remaining = late_hours - ot_used
            al_used = min(remaining, max(al_balance, 0.0))
            unpaid_hours = max(remaining - al_used, 0.0)

            self._update_unpaid_input(slip, "LATE_UNPAID_H", unpaid_hours)
            self._upsert_negative_allocation(slip, ot_type, ot_used, "late_reco_ot_alloc_id", _("OT used to cover lateness"))
            self._upsert_negative_allocation(slip, al_type, al_used, "late_reco_al_alloc_id", _("Annual Leave used to cover lateness"))
            slip.write({
                "late_reco_late_hours": late_hours,
                "late_reco_ot_hours": ot_used,
                "late_reco_al_hours": al_used,
                "late_reco_unpaid_hours": unpaid_hours,
            })

        return {'type': 'ir.actions.act_window_close'}
