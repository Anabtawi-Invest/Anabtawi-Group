# -*- coding: utf-8 -*-

from odoo import models, fields, api


class HrPayslipRun(models.Model):
    _inherit = "hr.payslip.run"

    # =====================================================
    # ENTERPRISE DASHBOARD KPIs (SAFE COMPUTE)
    # =====================================================

    dashboard_total_lateness = fields.Float(
        string="Total Lateness (h)",
        compute="_compute_dashboard_kpis",
        store=False,
    )

    dashboard_total_overtime = fields.Float(
        string="Total Overtime (h)",
        compute="_compute_dashboard_kpis",
        store=False,
    )

    dashboard_total_remaining = fields.Float(
        string="Remaining Lateness (h)",
        compute="_compute_dashboard_kpis",
        store=False,
    )

    dashboard_coverage_pct = fields.Float(
        string="Coverage %",
        compute="_compute_dashboard_kpis",
        store=False,
    )

    dashboard_slips_count = fields.Integer(
        string="Payslips",
        compute="_compute_dashboard_kpis",
        store=False,
    )

    dashboard_slips_with_lateness = fields.Integer(
        string="With Lateness",
        compute="_compute_dashboard_kpis",
        store=False,
    )

    dashboard_slips_remaining = fields.Integer(
        string="Remaining",
        compute="_compute_dashboard_kpis",
        store=False,
    )

    # =====================================================
    # KPI COMPUTE
    # =====================================================

    @api.depends("slip_ids")
    def _compute_dashboard_kpis(self):

        for run in self:
            slips = run.slip_ids

            total_lateness = 0.0
            total_ot = 0.0
            total_remaining = 0.0

            slips_with_lateness = 0

            for slip in slips:
                late = getattr(slip, "dashboard_lateness_hours", 0.0)
                ot = getattr(slip, "dashboard_ot_hours", 0.0)
                remaining = getattr(slip, "dashboard_remaining", 0.0)

                total_lateness += late
                total_ot += ot
                total_remaining += remaining

                if late > 0:
                    slips_with_lateness += 1

            run.dashboard_total_lateness = total_lateness
            run.dashboard_total_overtime = total_ot
            run.dashboard_total_remaining = total_remaining
            run.dashboard_slips_count = len(slips)
            run.dashboard_slips_with_lateness = slips_with_lateness
            run.dashboard_slips_remaining = sum(
                1 for s in slips if getattr(s, "dashboard_remaining", 0.0) > 0
            )

            if total_lateness:
                run.dashboard_coverage_pct = (
                    (total_lateness - total_remaining) / total_lateness
                ) * 100.0
            else:
                run.dashboard_coverage_pct = 0.0

    # =====================================================
    # 🔥 ENTERPRISE MASS RECONCILIATION ENGINE
    # =====================================================

    def action_mass_reconcile_lateness_enterprise(self):
        """
        ULTRA SAFE ENTERPRISE RECONCILIATION

        RULES:
        - Uses dashboard fields already computed from work entries
        - Does NOT modify salary rules
        - Does NOT recompute payroll engine
        - Only updates OT bank / remaining lateness fields
        """

        for run in self:
            slips = run.slip_ids

            for slip in slips:

                lateness = getattr(slip, "dashboard_lateness_hours", 0.0)
                ot_bank = getattr(slip, "dashboard_ot_bank", 0.0)

                if not lateness:
                    continue

                # =====================================================
                # STEP 1 — OFFSET LATENESS WITH OT BANK
                # =====================================================

                if ot_bank >= lateness:
                    remaining = 0.0
                    new_ot_bank = ot_bank - lateness
                else:
                    remaining = lateness - ot_bank
                    new_ot_bank = 0.0

                # =====================================================
                # STEP 2 — WRITE RESULTS (SAFE WRITE)
                # =====================================================

                values = {}

                if "dashboard_remaining" in slip._fields:
                    values["dashboard_remaining"] = remaining

                if "dashboard_ot_bank" in slip._fields:
                    values["dashboard_ot_bank"] = new_ot_bank

                if values:
                    slip.write(values)

        # =====================================================
        # STEP 3 — FORCE UI REFRESH (ENTERPRISE SAFE)
        # =====================================================

        return {
            "type": "ir.actions.client",
            "tag": "reload",
        }
