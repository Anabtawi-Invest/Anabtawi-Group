from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class DirectSalesCashHandoverWizard(models.TransientModel):
    _name = "direct.sales.cash.handover.wizard"
    _description = "Salesperson Cash Handover Wizard"

    user_id = fields.Many2one(
        "res.users",
        string="Salesperson / Cash Van Driver",
        required=True,
        default=lambda self: self.env.user,
    )
    salesperson_cash_journal_id = fields.Many2one(
        related="user_id.salesperson_cash_journal_id",
        string="Salesperson Custodian Journal",
        readonly=True,
    )
    current_wallet_balance = fields.Float(
        related="user_id.cash_wallet_balance",
        string="Total Cash Collected (Wallet Balance)",
        readonly=True,
    )
    amount_handed_over = fields.Float(
        string="Physical Cash Handed Over",
        required=True,
    )
    destination_journal_id = fields.Many2one(
        "account.journal",
        string="Destination Safe / Main Cash Journal",
        required=True,
        domain="[('type', 'in', ('cash', 'bank')), ('company_id', '=', company_id)]",
    )
    remaining_balance = fields.Float(
        string="Remaining Balance Owed by Salesperson",
        compute="_compute_remaining_balance",
        readonly=True,
    )
    company_id = fields.Many2one(
        "res.company",
        default=lambda self: self.env.company,
        required=True,
    )
    currency_id = fields.Many2one(
        "res.currency",
        related="company_id.currency_id",
    )
    notes = fields.Text(string="Handover Notes / Memo")

    @api.onchange("user_id")
    def _onchange_user_id(self):
        if self.user_id:
            self.amount_handed_over = self.user_id.cash_wallet_balance

    @api.depends("current_wallet_balance", "amount_handed_over")
    def _compute_remaining_balance(self):
        for wizard in self:
            wizard.remaining_balance = max(0.0, wizard.current_wallet_balance - wizard.amount_handed_over)

    def action_confirm_handover(self):
        self.ensure_one()
        if self.amount_handed_over <= 0:
            raise UserError(_("Handover amount must be greater than zero."))
        if not self.user_id.salesperson_cash_journal_id:
            journal = self.env["account.journal"].sudo().search([
                ("type", "=", "cash"),
                ("company_id", "=", self.company_id.id),
                ("name", "ilike", self.user_id.name),
            ], limit=1)
            if not journal:
                journal = self.env["account.journal"].sudo().create({
                    "name": _("Custodian Cash - %s") % self.user_id.name,
                    "code": f"CASH{self.user_id.id}",
                    "type": "cash",
                    "company_id": self.company_id.id,
                })
            self.user_id.sudo().salesperson_cash_journal_id = journal

        from_journal = self.user_id.salesperson_cash_journal_id
        to_journal = self.destination_journal_id

        payment = self.env["account.payment"].sudo().create({
            "payment_type": "outbound",
            "is_internal_transfer": True,
            "amount": self.amount_handed_over,
            "journal_id": from_journal.id,
            "destination_journal_id": to_journal.id,
            "date": fields.Date.context_today(self),
            "ref": _("Cash Handover from %s - Memo: %s") % (self.user_id.name, self.notes or _("End of Day Handover")),
            "company_id": self.company_id.id,
        })
        payment.action_post()

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Cash Handover Confirmed"),
                "message": _(
                    "Handed over %s %s to %s. Remaining salesperson balance: %s %s.",
                    self.amount_handed_over,
                    self.currency_id.name,
                    to_journal.display_name,
                    self.remaining_balance,
                    self.currency_id.name,
                ),
                "sticky": False,
                "type": "success",
            },
        }
