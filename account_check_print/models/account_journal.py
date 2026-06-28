from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class AccountJournal(models.Model):
    """Add per-bank check stock, layout, language, and numbering settings."""

    _inherit = "account.journal"

    enable_check_printing = fields.Boolean(
        string="Enable Check Printing",
        help="Allow outgoing business checks to be printed from this bank journal.",
    )
    check_layout_id = fields.Many2one(
        "account.check.layout",
        check_company=True,
        domain="[('company_id', '=', company_id)]",
        ondelete="restrict",
    )
    next_check_number = fields.Integer(default=1, copy=False)
    print_language = fields.Selection(
        [("en", "English"), ("ar", "Arabic")], required=True, default="en"
    )
    stock_type = fields.Selection(
        [("blank", "Blank Stock"), ("preprinted", "Pre-printed Stock")],
        required=True,
        default="preprinted",
    )

    @api.onchange("enable_check_printing")
    def _onchange_enable_check_printing(self):
        """Suggest the first company layout when check printing is enabled."""
        if self.enable_check_printing and not self.check_layout_id:
            self.check_layout_id = self.env["account.check.layout"].search(
                [("company_id", "=", self.company_id.id)], limit=1
            )

    @api.constrains("enable_check_printing", "check_layout_id", "next_check_number")
    def _check_check_printing_configuration(self):
        """Require a layout and a usable next number on enabled journals."""
        for journal in self:
            if journal.enable_check_printing and not journal.check_layout_id:
                raise ValidationError(
                    _("A check layout is required when check printing is enabled.")
                )
            if journal.enable_check_printing and journal.next_check_number < 1:
                raise ValidationError(_("The next check number must be greater than zero."))
