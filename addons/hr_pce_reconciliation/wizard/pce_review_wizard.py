from odoo import models, fields, api, _
from odoo.exceptions import UserError

def _sf(v):
    try:
        return float(v or 0.0)
    except Exception:
        return 0.0

class PcePayrunReviewWizard(models.TransientModel):
    _name = "pce.payrun.review.wizard"
    _description = "PCE Smart Review (Payrun)"

    run_id = fields.Many2one("hr.payslip.run", required=True, readonly=True)
    line_ids = fields.One2many("pce.payrun.review.line", "wizard_id", readonly=True)

    to_reconcile_count = fields.Integer(compute="_compute_counts", store=False)
    need_salary_deduction_count = fields.Integer(compute="_compute_counts", store=False)

    @api.depends("line_ids")
    def _compute_counts(self):
        for wiz in self:
            wiz.to_reconcile_count = len(wiz.line_ids.filtered(lambda l: l.review_status != "ok"))
            wiz.need_salary_deduction_count = len(wiz.line_ids.filtered(lambda l: l.review_status == "need_salary_deduction"))

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        run_id = res.get("run_id") or self.env.context.get("default_run_id") or self.env.context.get("active_id")
        if not run_id:
            return res
        run = self.env["hr.payslip.run"].browse(run_id).exists()
        if not run:
            return res
        res["run_id"] = run.id
        lines = []
        for slip in run.slip_ids:
            lines.append((0, 0, {
                "payslip_id": slip.id,
                "employee_id": slip.employee_id.id,
                "employee_barcode": slip.employee_id.barcode or "",
                "employee_identification_id": slip.employee_id.identification_id or "",
                "lateness_hours": _sf(slip.lateness_hours),
                "ot_total_hours": _sf(slip.ot_total_hours),
                "annual_leave_hours": _sf(slip.annual_leave_hours),
                "bank_before_hours": _sf(slip.pce_bank_before_hours or slip.employee_id.pce_ot_bank_hours),
                "bank_after_hours": _sf(slip.pce_bank_after_hours),
                "remaining_hours": _sf(slip.remaining_after_reconciliation_hours),
                "review_status": slip.pce_review_status,
                "reconciled": (slip.reconciliation_state == "done"),
            }))
        res["line_ids"] = lines
        return res

    def action_reconcile_all(self):
        self.ensure_one()
        if not self.run_id:
            raise UserError(_("Missing payrun."))
        self.run_id.slip_ids.action_reconcile_lateness()
        # Refresh wizard lines (re-open)
        return self.run_id.action_open_pce_smart_review()

class PcePayrunReviewLine(models.TransientModel):
    _name = "pce.payrun.review.line"
    _description = "PCE Smart Review Line"
    _order = "review_status, employee_id"

    wizard_id = fields.Many2one("pce.payrun.review.wizard", required=True, ondelete="cascade")
    payslip_id = fields.Many2one("hr.payslip", readonly=True)
    employee_id = fields.Many2one("hr.employee", readonly=True)

    employee_barcode = fields.Char(readonly=True)
    employee_identification_id = fields.Char(readonly=True)

    lateness_hours = fields.Float(readonly=True)
    ot_total_hours = fields.Float(readonly=True)
    annual_leave_hours = fields.Float(readonly=True)
    bank_before_hours = fields.Float(readonly=True)
    bank_after_hours = fields.Float(readonly=True)
    remaining_hours = fields.Float(readonly=True)

    reconciled = fields.Boolean(readonly=True)
    review_status = fields.Selection(
        [("ok", "OK"), ("need_reconcile", "To Reconcile"), ("need_salary_deduction", "Needs Salary Deduction")],
        readonly=True,
    )
