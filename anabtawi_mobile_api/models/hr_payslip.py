import logging

from odoo import _, models

_logger = logging.getLogger(__name__)


class HrPayslip(models.Model):
    _inherit = "hr.payslip"

    def action_payslip_done(self, *args, **kwargs):
        """Tell the employee once HR confirms the payslip.

        The Employee App only lists payslips in state done/paid, so this is
        also the moment the payslip becomes visible in the app.
        """
        before = {slip.id: slip.state for slip in self}
        res = super().action_payslip_done(*args, **kwargs)
        Notification = self.env["anabtawi.mobile.notification"]
        for slip in self:
            if before.get(slip.id) == "done" or slip.state not in ("done", "paid"):
                continue
            user = slip.employee_id.user_id
            if not user:
                continue
            Notification.push(
                user, "payslip", _("Your payslip is ready"),
                "%s - %s" % (slip.date_from or "", slip.date_to or ""),
                record=slip,
            )
        return res
