# -*- coding: utf-8 -*-
from odoo import models, _
from odoo.exceptions import ValidationError


class HrPayslip(models.Model):
    _inherit = 'hr.payslip'

    def _recompute_paid_cycle(self):
        """Unpaid, cancel, draft, compute sheet, validate, paid. One payslip."""
        self.ensure_one()
        slip = self.with_context(
            tracking_disable=True, mail_notrack=True, mail_create_nolog=True,
            mail_activity_automation_skip=True,
        )
        if slip.state == 'paid':
            slip.action_payslip_unpaid()
        slip.invalidate_recordset()
        if slip.state == 'validated':
            slip.action_payslip_cancel()
        slip.invalidate_recordset()
        if slip.state == 'cancel':
            slip.action_payslip_draft()
        slip.invalidate_recordset()
        if slip.state == 'draft':
            slip.compute_sheet()
        slip.invalidate_recordset()
        if slip.error_count:
            raise ValidationError(slip._get_error_message() or _("Payslip has errors."))
        if slip.state == 'draft':
            slip.action_payslip_done()
        slip.invalidate_recordset()
        if slip.state == 'validated':
            slip.action_payslip_paid()
