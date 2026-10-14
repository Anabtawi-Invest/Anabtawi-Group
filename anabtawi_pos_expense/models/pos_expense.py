from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError


class PosExpense(models.Model):
    _name = "pos.expense"
    _description = "POS Expense"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date desc, id desc"

    name = fields.Char(string="Reference", required=True, copy=False, readonly=True, default=lambda self: _("New"))
    date = fields.Datetime(required=True, readonly=True, default=fields.Datetime.now)
    config_id = fields.Many2one("pos.config", string="Point of Sale", required=True, readonly=True, index=True)
    session_id = fields.Many2one("pos.session", string="Session", readonly=True, index=True)
    company_id = fields.Many2one(related="config_id.company_id", store=True, index=True)
    currency_id = fields.Many2one(related="config_id.currency_id")
    type_id = fields.Many2one("pos.expense.type", string="Expense Type", required=True, readonly=True)
    amount = fields.Monetary(required=True, readonly=True)
    user_id = fields.Many2one("res.users", string="User", readonly=True, default=lambda self: self.env.user)
    cashier_name = fields.Char(string="Cashier", readonly=True)
    image = fields.Image(string="Receipt Photo", max_width=1920, max_height=1920, readonly=True)
    state = fields.Selection(
        [
            ("to_approve", "To Approve"),
            ("approved", "Approved"),
            ("refused", "Refused"),
        ],
        string="Status",
        required=True,
        readonly=True,
        default="to_approve",
        tracking=True,
        index=True,
    )
    statement_line_id = fields.Many2one(
        "account.bank.statement.line",
        string="Cash Out",
        readonly=True,
        copy=False,
    )
    move_id = fields.Many2one(related="statement_line_id.move_id", string="Journal Entry")
    decided_by_id = fields.Many2one("res.users", string="Approved/Refused By", readonly=True, copy=False)
    decision_date = fields.Datetime(string="Approval/Refusal Date", readonly=True, copy=False)
    refuse_reason = fields.Char(tracking=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", _("New")) == _("New"):
                vals["name"] = self.env["ir.sequence"].next_by_code("pos.expense") or _("New")
        return super().create(vals_list)

    def _check_approver(self):
        if not self.env.user.has_group("point_of_sale.group_pos_manager"):
            raise AccessError(_("Only Point of Sale managers can approve or refuse expenses."))
        if self.filtered(lambda e: e.state != "to_approve"):
            raise UserError(_("Only expenses waiting for approval can be approved or refused."))

    def _set_decision(self, state):
        self._check_approver()
        self.write({
            "state": state,
            "decided_by_id": self.env.user.id,
            "decision_date": fields.Datetime.now(),
        })
        self.config_id.invalidate_recordset(["expense_pending_amount", "expense_available_amount"])

    def action_approve(self):
        self._set_decision("approved")

    def action_refuse(self):
        self._set_decision("refused")

    def action_open_move(self):
        self.ensure_one()
        return self.move_id._get_records_action()
