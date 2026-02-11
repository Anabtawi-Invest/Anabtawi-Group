# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class HrPayslipRun(models.Model):
    _inherit = "hr.payslip.run"

    dashboard_total_lateness = fields.Float(string="Total Lateness (h)", digits=(16, 2),
                                           compute="_compute_dashboard_totals", store=False, readonly=True)
    dashboard_total_overtime = fields.Float(string="Total Overtime (h)", digits=(16, 2),
                                           compute="_compute_dashboard_totals", store=False, readonly=True)
    dashboard_total_remaining = fields.Float(string="Total Remaining (h)", digits=(16, 2),
                                            compute="_compute_dashboard_totals", store=False, readonly=True)
    dashboard_coverage_pct = fields.Float(string="Coverage %", digits=(16, 2),
                                         compute="_compute_dashboard_totals", store=False, readonly=True)
    dashboard_slips_count = fields.Integer(string="Payslips", compute="_compute_dashboard_totals", store=False, readonly=True)
    dashboard_slips_with_lateness = fields.Integer(string="With Lateness", compute="_compute_dashboard_totals", store=False, readonly=True)
    dashboard_slips_remaining = fields.Integer(string="Remaining > 0", compute="_compute_dashboard_totals", store=False, readonly=True)

    @api.depends("slip_ids.dashboard_lateness_hours", "slip_ids.dashboard_ot_hours",
                 "slip_ids.dashboard_remaining", "slip_ids.state")
    def _compute_dashboard_totals(self):
        for run in self:
            slips = run.slip_ids
            run.dashboard_slips_count = len(slips)
            total_l = sum(slips.mapped("dashboard_lateness_hours")) if slips else 0.0
            total_ot = sum(slips.mapped("dashboard_ot_hours")) if slips else 0.0
            total_r = sum(slips.mapped("dashboard_remaining")) if slips else 0.0

            run.dashboard_total_lateness = total_l
            run.dashboard_total_overtime = total_ot
            run.dashboard_total_remaining = total_r

            with_lateness = slips.filtered(lambda s: (s.dashboard_lateness_hours or 0.0) > 0.0)
            remaining = slips.filtered(lambda s: (s.dashboard_remaining or 0.0) > 0.0)
            run.dashboard_slips_with_lateness = len(with_lateness)
            run.dashboard_slips_remaining = len(remaining)

            if total_l <= 0:
                run.dashboard_coverage_pct = 100.0
            else:
                covered = max(total_l - total_r, 0.0)
                pct = (covered / total_l) * 100.0
                run.dashboard_coverage_pct = min(max(pct, 0.0), 100.0)

    def action_mass_reconcile_lateness_enterprise(self):
        """FINAL enterprise action:
        - Runs your existing per-slip reconciliation method if present
        - Recomputes dashboard fields (stored) for immediate list update
        - Posts a summary to chatter
        - Reloads UI (Odoo 19 Owl)
        """
        slips = self.env["hr.payslip"].browse(self.env.context.get("active_ids", []))
        if not slips:
            raise UserError(_("No payslips selected."))

        # Only draft slips should be reconciled; keep behavior strict and predictable
        slips = slips.filtered(lambda s: s.state == "draft")
        if not slips:
            raise UserError(_("No draft payslips selected."))

        # Run existing reconciliation (from your original module) if present
        for slip in slips:
            if hasattr(slip, "_lateness_reconcile_for_slip"):
                slip._lateness_reconcile_for_slip()

        # Recompute dashboard stored fields for immediate UI update
        slips._recompute_dashboard_fields()

        # Build summary
        total_l = sum(slips.mapped("dashboard_lateness_hours"))
        total_r = sum(slips.mapped("dashboard_remaining"))
        covered = max(total_l - total_r, 0.0)
        pct = 100.0 if total_l <= 0 else min(max((covered / total_l) * 100.0, 0.0), 100.0)

        # Post on the pay run chatter if we can infer it; otherwise post generic
        pay_runs = slips.mapped("payslip_run_id")
        msg = _(
            "Mass Reconcile Lateness executed on %(n)s payslip(s). "
            "Total Lateness: %(tl).2f h | Covered: %(cv).2f h | Remaining: %(tr).2f h | Coverage: %(pc).2f%%"
        ) % {"n": len(slips), "tl": total_l, "cv": covered, "tr": total_r, "pc": pct}

        for run in pay_runs:
            run.message_post(body=msg)

        return {"type": "ir.actions.client", "tag": "reload"}
