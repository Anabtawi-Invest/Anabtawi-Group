# -*- coding: utf-8 -*-
from lxml import etree

from odoo import _, api, models
from odoo.exceptions import UserError


class HrPayslip(models.Model):
    _inherit = "hr.payslip"

    def _user_hides_payslip_action_buttons(self):
        return self.env.user.has_group(
            "payslip_hide_action_buttons.group_hide_payslip_action_buttons"
        )

    def _check_payslip_action_button_access(self):
        if self._user_hides_payslip_action_buttons():
            raise UserError(_("You are not allowed to use payslip action buttons."))

    @api.model
    def get_view(self, view_id=None, view_type="form", **options):
        res = super().get_view(view_id=view_id, view_type=view_type, **options)
        if view_type not in ("form", "list") or not self._user_hides_payslip_action_buttons():
            return res

        arch = etree.fromstring(res["arch"])
        keep_names = {
            "action_export_payslip",                 # Export XLSX
            "action_export_payrun_excel",            # PayRun Audit
            "compute_sheet",                         # Compute Sheet
            "action_export_bank_xlsx",               # Export Bank File
            "action_reconcile_lateness_no_ot_bank",  # Reconcile Lateness
            "action_reset_lateness_reconciliation",  # Reset Reconciliation
            "action_print_payslip",                  # Print (method)
        }
        keep_strings = {
            "Print",
            "Export Bank File",
            "Reconcile Lateness",
            "Reset Reconciliation",
        }
        for button in arch.xpath("//header/button"):
            name = button.get("name") or ""
            string = (button.get("string") or "").strip()
            if name in keep_names or string in keep_strings:
                continue
            # Keep report Print buttons: name is often a report action xmlid/id
            if string == "Print" or "report_payslip" in name or name.endswith("action_report_payslip"):
                continue
            button.getparent().remove(button)
        res["arch"] = etree.tostring(arch, encoding="unicode")
        return res

    def action_payslip_done(self):
        self._check_payslip_action_button_access()
        return super().action_payslip_done()

    def action_validate(self):
        self._check_payslip_action_button_access()
        return super().action_validate()

    def action_payslip_paid(self):
        self._check_payslip_action_button_access()
        return super().action_payslip_paid()

    def action_payslip_unpaid(self):
        self._check_payslip_action_button_access()
        return super().action_payslip_unpaid()

    def action_payslip_draft(self):
        self._check_payslip_action_button_access()
        return super().action_payslip_draft()

    def action_payslip_cancel(self):
        self._check_payslip_action_button_access()
        return super().action_payslip_cancel()

    def refund_sheet(self):
        self._check_payslip_action_button_access()
        return super().refund_sheet()
