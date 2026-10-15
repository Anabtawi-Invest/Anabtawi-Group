from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

# Expenses in these states still consume the POS expense limit.
OPEN_STATES = ("to_approve", "refused")


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
    image_256 = fields.Image(string="Receipt Thumbnail", related="image", max_width=256, max_height=256, store=True)
    state = fields.Selection(
        [
            ("to_approve", "To Approve"),
            ("approved", "Approved"),
            ("refused", "Refused"),
            ("resent", "Resent"),
            ("returned", "Returned"),
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
    resubmit_count = fields.Integer(string="Resubmitted", readonly=True, copy=False)
    adjustment_statement_line_ids = fields.Many2many(
        "account.bank.statement.line",
        "pos_expense_adjustment_statement_line_rel",
        "expense_id",
        "statement_line_id",
        string="Amount Adjustments",
        readonly=True,
        copy=False,
    )

    return_session_id = fields.Many2one("pos.session", string="Returned in Session", readonly=True, copy=False)
    return_cashier_name = fields.Char(string="Returned By", readonly=True, copy=False)
    return_date = fields.Datetime(string="Return Date", readonly=True, copy=False)
    return_statement_line_id = fields.Many2one(
        "account.bank.statement.line",
        string="Cash In (Return)",
        readonly=True,
        copy=False,
    )
    return_move_id = fields.Many2one(related="return_statement_line_id.move_id", string="Return Journal Entry")

    original_expense_id = fields.Many2one(
        "pos.expense",
        string="Original Expense",
        readonly=True,
        copy=False,
        index="btree_not_null",
        help="The refused expense this one was resent from.",
    )
    resent_expense_ids = fields.One2many("pos.expense", "original_expense_id", string="Resent As", readonly=True)
    resent_expense_count = fields.Integer(compute="_compute_resent_expense_count")
    chain_move_ids = fields.Many2many(
        "account.move",
        string="Journal Entries",
        compute="_compute_chain_move_ids",
        help="Cash out, adjustments and return entries of this expense and of all its resent versions.",
    )
    chain_move_count = fields.Integer(compute="_compute_chain_move_ids")

    @api.depends("resent_expense_ids")
    def _compute_resent_expense_count(self):
        for expense in self:
            expense.resent_expense_count = len(expense.resent_expense_ids)

    def _get_chain(self):
        """All expenses linked to ``self`` through resends (originals and resent versions)."""
        self.ensure_one()
        root = self
        while root.original_expense_id:
            root = root.original_expense_id
        chain = root
        current = root
        while current:
            current = current.resent_expense_ids
            chain |= current
        return chain

    @api.depends(
        "original_expense_id", "resent_expense_ids",
        "statement_line_id", "adjustment_statement_line_ids", "return_statement_line_id",
    )
    def _compute_chain_move_ids(self):
        for expense in self:
            chain = expense.sudo()._get_chain() if expense.id else expense
            lines = (
                chain.statement_line_id
                | chain.adjustment_statement_line_ids
                | chain.return_statement_line_id
            )
            moves = lines.move_id.sorted(lambda m: (m.date, m.id))
            expense.chain_move_ids = moves
            expense.chain_move_count = len(moves)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", _("New")) == _("New"):
                vals["name"] = self.env["ir.sequence"].next_by_code("pos.expense") or _("New")
        return super().create(vals_list)

    def _invalidate_config_balance(self):
        self.config_id.invalidate_recordset(["expense_pending_amount", "expense_available_amount"])

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
        self._invalidate_config_balance()

    def action_approve(self):
        self._set_decision("approved")

    def action_refuse(self):
        missing_reason = self.filtered(lambda e: not (e.refuse_reason or "").strip())
        if missing_reason:
            raise UserError(_(
                "Please fill the Refuse Reason before refusing: %s",
                ", ".join(missing_reason.mapped("name")),
            ))
        self._set_decision("refused")

    def action_open_journal_entries(self):
        self.ensure_one()
        return self.chain_move_ids._get_records_action(name=_("Journal Entries of %s", self.name))

    def action_open_original_expense(self):
        self.ensure_one()
        return self.original_expense_id._get_records_action()

    def action_open_resent_expenses(self):
        self.ensure_one()
        return self.resent_expense_ids._get_records_action(name=_("Resent As"))

    def _get_image_thumbnail(self):
        self.ensure_one()
        thumbnail = self.image_256
        if isinstance(thumbnail, bytes):
            thumbnail = thumbnail.decode()
        return thumbnail or False

    def _prepare_pos_refused_data(self):
        return [
            {
                "id": expense.id,
                "name": expense.name,
                "type": expense.type_id.name,
                "type_id": expense.type_id.id,
                "amount": expense.amount,
                "image_thumbnail": expense._get_image_thumbnail(),
                "resubmit_count": expense.resubmit_count,
                "date": fields.Datetime.to_string(expense.date),
                "cashier_name": expense.cashier_name or "",
                "session_name": expense.session_id.name or "",
                "refuse_reason": expense.refuse_reason or "",
            }
            for expense in self
        ]
