import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class AnabtawiMobileNotification(models.Model):
    """In-app inbox for the Employee App (leave approvals, payslips, ...).

    Rows are written server side by workflow hooks and read through the
    Employee App API, which polls /anabtawi/mobile/notifications/count.
    """

    _name = "anabtawi.mobile.notification"
    _description = "Employee App Notification"
    _order = "id desc"

    user_id = fields.Many2one("res.users", required=True, index=True, ondelete="cascade")
    kind = fields.Selection(
        [
            ("leave_request", "Leave request to approve"),
            ("leave_hr", "Leave waiting for HR"),
            ("leave_approved", "Leave approved by manager"),
            ("leave_validated", "Leave confirmed by HR"),
            ("leave_refused", "Leave refused"),
            ("payslip", "Payslip ready"),
            ("info", "Information"),
        ],
        required=True,
        default="info",
    )
    title = fields.Char(required=True)
    body = fields.Char()
    res_model = fields.Char()
    res_id = fields.Integer()
    is_read = fields.Boolean(default=False, index=True)
    read_at = fields.Datetime()

    def init(self):
        self.env.cr.execute(
            "CREATE INDEX IF NOT EXISTS anabtawi_mobile_notification_user_read_idx "
            "ON anabtawi_mobile_notification (user_id, is_read, id DESC)"
        )

    @api.model
    def push(self, users, kind, title, body="", record=None):
        """Create one notification per user. Never raises: a notification
        failure must not break the business workflow that triggered it."""
        users = users.filtered(lambda user: user.active)
        if not users:
            return self.browse()
        vals = [{
            "user_id": user.id,
            "kind": kind,
            "title": title,
            "body": body or False,
            "res_model": record._name if record else False,
            "res_id": record.id if record else 0,
        } for user in users]
        try:
            with self.env.cr.savepoint():
                return self.sudo().create(vals)
        except Exception:
            _logger.exception("Employee App notification failed: kind=%s", kind)
            return self.browse()

    @api.model
    def mark_read(self, user, ids=None):
        domain = [("user_id", "=", user.id), ("is_read", "=", False)]
        if ids:
            domain.append(("id", "in", ids))
        rows = self.sudo().search(domain)
        rows.write({"is_read": True, "read_at": fields.Datetime.now()})
        return len(rows)

    @api.autovacuum
    def _gc_old_notifications(self):
        limit = fields.Datetime.subtract(fields.Datetime.now(), days=90)
        self.sudo().search([("is_read", "=", True), ("create_date", "<", limit)]).unlink()
