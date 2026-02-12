# -*- coding: utf-8 -*-

from odoo import models, fields, api


class HrPayslipRun(models.Model):
    _inherit = "hr.payslip.run"

    # =====================================================
    # ENTERPRISE KPI FIELDS
    # =====================================================

    total_lateness = fields.Float(
        string="Total Lateness (h)",
        compute="_compute_kpis",
        store=False,
    )

    total_overtime = fields.Float(
        string="Total Overtime (h)",
        compute="_compute_kpis",
        store=False,
    )

    total_remaining = fields.Float(
        string="Remaining Lateness (h)",
        compute="_compute_kpis",
        store=False,
    )

    coverage_pct = fields.Float(
        string="Coverage %",
        compute="_compute_kpis",
        store=False,
    )

    slips_count = fields.Integer(
        string="Payslips",
        compute="_compute_kpis",
        store=False,
    )

    slips_with_lateness = fields.Integer(
        string="With Lateness",
        compute="_compute_kpis",
        store=False,
    )

    slips_remaining = fields.Integer(
        string="Remaining",
        compute="_compute_kpis",
        store=False,
    )

    # =====================================================
    # KPI COMPUTE (USES NEW FIELD NAMES)
    # =====================================================

    @api.depends("slip_ids")
    def _compute_kpis(self):

        for run in self:
            slips = run.slip_ids

            total_lateness = 0.0
            total_ot = 0.0
            total_remaining = 0.0

            slips_with_lateness = 0
            slips_remaining = 0

            for slip in slips:

                late = getattr(slip, "lateness_hours", 0.0)
                ot = getattr(slip, "ot_hours", 0.0)
                remaining = getattr(slip, "remaining_hours", 0.0)

                total_lateness += late
                total_ot += ot
                total_remaining += remaining

                if late > 0:
                    slips_with_lateness += 1

                if remaining > 0:
                    slips_remaining += 1

            run.total_lateness = total_lateness
            run.total_overtime = total_ot
            run.total_remaining = total_remaining
            run.slips_count = len(slips)
            run.slips_with_lateness = slips_with_lateness
            run.slips_remaining = slips_remaining

            if total_lateness:
                run.coverage_pct = (
                    (total_lateness - total_remaining) / total_lateness
                ) * 100.0
            else:
                run.coverage_pct = 0.0

    # =====================================================
    # 🔥 ENTERPRISE MASS RECONCILIATION ENGINE
    # =====================================================

    def action_mass_reconcile_lateness_enterprise(self):
        """
        ENTERPRISE SAFE RECONCILIATION

        - Uses lateness_hours + ot_bank fields
        - Does NOT touch payroll engine
        - Updates remaining_hours + ot_bank only
        """

        for run in self:
            for slip in run.slip_ids:

                lateness = getattr(slip, "lateness_hours", 0.0)
                ot_bank = getattr(slip, "ot_bank", 0.0)

                if not lateness:
                    continue

                # Offset lateness with OT bank
                if ot_bank >= lateness:
                    remaining = 0.0
                    new_ot_bank = ot_bank - lateness
                else:
                    remaining = lateness - ot_bank
                    new_ot_bank = 0.0

                values = {}

                if "remaining_hours" in slip._fields:
                    values["remaining_hours"] = remaining

                if "ot_bank" in slip._fields:
                    values["ot_bank"] = new_ot_bank

                if values:
                    slip.write(values)

        # Enterprise UI refresh
        return {
            "type": "ir.actions.client",
            "tag": "reload",
        }
