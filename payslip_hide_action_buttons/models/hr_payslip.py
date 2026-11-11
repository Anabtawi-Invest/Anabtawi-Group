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
        keep_names = {"action_export_payslip"}
        for button in arch.xpath("//header/button"):
            if button.get("name") in keep_names:
                continue
            button.getparent().remove(button)
        res["arch"] = etree.tostring(arch, encoding="unicode")
        return res

    def compute_sheet(self):
        self._check_payslip_action_button_access()
        return super().compute_sheet()

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
