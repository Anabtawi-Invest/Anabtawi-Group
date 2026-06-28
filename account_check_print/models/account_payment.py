from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


class AccountPayment(models.Model):
    """Implement the auditable lifecycle of outgoing business checks."""

    _inherit = "account.payment"

    check_number = fields.Char(copy=False, readonly=True, index=True, tracking=True)
    printed = fields.Boolean(copy=False, readonly=True, tracking=True)
    printed_date = fields.Datetime(copy=False, readonly=True)
    printed_by = fields.Many2one("res.users", copy=False, readonly=True)
    voided = fields.Boolean(copy=False, readonly=True, tracking=True)
    reprinted_count = fields.Integer(copy=False, readonly=True)
    check_layout_snapshot = fields.Json(copy=False, readonly=True)
    check_history_ids = fields.One2many(
        "account.check.print.history", "payment_id", readonly=True
    )
    check_history_count = fields.Integer(compute="_compute_check_history_count")
    can_print_check = fields.Boolean(compute="_compute_check_permissions")
    can_preview_check = fields.Boolean(compute="_compute_check_permissions")

    _journal_check_number_unique = models.Constraint(
        "UNIQUE(journal_id, check_number)",
        "A check number can only be used once per bank journal.",
    )

    @api.depends("check_history_ids")
    def _compute_check_history_count(self):
        """Compute the number shown on the payment smart button."""
        for payment in self:
            payment.check_history_count = len(payment.check_history_ids)

    def _compute_check_permissions(self):
        """Expose button visibility without granting server-side authority."""
        is_manager = self.env.user.has_group("account.group_account_manager")
        is_accountant = self.env.user.has_group("account.group_account_user")
        for payment in self:
            configured = payment._is_check_printing_configured()
            payment.can_preview_check = is_accountant and configured
            payment.can_print_check = is_manager and configured

    def _is_check_printing_configured(self):
        """Return whether this payment belongs to an enabled bank journal."""
        self.ensure_one()
        return bool(
            self.payment_type == "outbound"
            and self.journal_id.type == "bank"
            and self.journal_id.enable_check_printing
            and self.journal_id.check_layout_id
        )

    def _check_print_access(self):
        """Require Accounting Manager rights for lifecycle mutations."""
        if not self.env.user.has_group("account.group_account_manager"):
            raise AccessError(_("Only Accounting Managers can print, reprint, or void checks."))

    def _check_preview_access(self):
        """Require Accounting User rights for non-mutating previews."""
        if not self.env.user.has_group("account.group_account_user"):
            raise AccessError(_("Only Accounting Users can preview checks."))

    def _validate_check_configuration(self, require_posted=False):
        """Validate payment direction, journal configuration, and lifecycle state."""
        self.ensure_one()
        if self.payment_type != "outbound":
            raise UserError(_("Checks can only be issued for outgoing payments."))
        if self.journal_id.type != "bank":
            raise UserError(_("Checks can only be printed from a bank journal."))
        if not self.journal_id.enable_check_printing:
            raise UserError(_("Check printing is not enabled on this bank journal."))
        if not self.journal_id.check_layout_id:
            raise UserError(_("Select a check layout on the bank journal first."))
        if require_posted and self.state not in ("in_process", "paid"):
            raise UserError(_("Confirm the payment before printing its check."))
        if self.amount <= 0:
            raise UserError(_("A check amount must be greater than zero."))
        if self.voided:
            raise UserError(_("A voided check cannot be printed."))

    def _layout_snapshot_values(self):
        """Capture report geometry so later layout edits cannot move a printed check."""
        self.ensure_one()
        layout = self.journal_id.check_layout_id
        values = {
            "layout_id": layout.id,
            "font_size": layout.font_size,
            "paper_width": layout.paper_width,
            "paper_height": layout.paper_height,
        }
        for name in layout._designer_field_names():
            for key in ("x", "y", "width", "height"):
                values[f"{name}_{key}"] = layout[f"{name}_{key}"]
        return values

    def _reserve_check_number(self):
        """Atomically reserve this journal's next check number."""
        self.ensure_one()
        journal = self.journal_id
        self.env.cr.execute(
            "SELECT next_check_number FROM account_journal WHERE id = %s FOR UPDATE",
            [journal.id],
        )
        row = self.env.cr.fetchone()
        if not row or row[0] < 1:
            raise ValidationError(_("The next check number must be greater than zero."))
        number = row[0]
        journal.next_check_number = number + 1
        return str(number)

    def _log_check_event(self, event_type, reason=None):
        """Append one immutable check audit event."""
        self.ensure_one()
        return self.env["account.check.print.history"].create({
            "payment_id": self.id,
            "check_number": self.check_number,
            "event_type": event_type,
            "user_id": self.env.user.id,
            "reason": reason,
        })

    def action_print_check(self):
        """Reserve a number, audit the first print, and return the PDF report."""
        self.ensure_one()
        self._check_print_access()
        self._validate_check_configuration(require_posted=True)
        if self.printed:
            raise UserError(_("This check was already printed. Use Reprint Check."))
        self.write({
            "check_number": self._reserve_check_number(),
            "printed": True,
            "printed_date": fields.Datetime.now(),
            "printed_by": self.env.user.id,
            "check_layout_snapshot": self._layout_snapshot_values(),
        })
        self._log_check_event("print")
        return self.env.ref("account_check_print.action_report_check").report_action(
            self.with_context(
                check_preview=False,
                active_model=self._name,
                active_id=self.id,
                active_ids=self.ids,
            )
        )

    def action_preview_check(self):
        """Render a watermarked check without consuming a number."""
        self.ensure_one()
        self._check_preview_access()
        self._validate_check_configuration()
        return self.env.ref("account_check_print.action_report_check").report_action(
            self.with_context(
                check_preview=True,
                active_model=self._name,
                active_id=self.id,
                active_ids=self.ids,
            )
        )

    def action_open_void_wizard(self):
        """Open the mandatory-reason void confirmation wizard."""
        self.ensure_one()
        self._check_print_access()
        if not self.printed or self.voided:
            raise UserError(_("Only a printed, active check can be voided."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Void Check"),
            "res_model": "account.check.void.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_payment_id": self.id},
        }

    def action_open_reprint_wizard(self):
        """Open the mandatory-reason reprint confirmation wizard."""
        self.ensure_one()
        self._check_print_access()
        if not self.printed or self.voided:
            raise UserError(_("Only a printed, active check can be reprinted."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Reprint Check"),
            "res_model": "account.check.reprint.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_payment_id": self.id},
        }

    def _void_check(self, reason):
        """Void the check while retaining its number and audit history."""
        self.ensure_one()
        self._check_print_access()
        if not reason or not reason.strip():
            raise ValidationError(_("A void reason is required."))
        if not self.printed or self.voided:
            raise UserError(_("Only a printed, active check can be voided."))
        self.voided = True
        self._log_check_event("void", reason.strip())
        return True

    def _reprint_check(self, reason):
        """Audit and render a replacement copy using the original number."""
        self.ensure_one()
        self._check_print_access()
        if not reason or not reason.strip():
            raise ValidationError(_("A reprint reason is required."))
        self._validate_check_configuration(require_posted=True)
        if not self.printed:
            raise UserError(_("Print the original check before reprinting it."))
        self.reprinted_count += 1
        self._log_check_event("reprint", reason.strip())
        return self.env.ref("account_check_print.action_report_check").report_action(
            self.with_context(
                check_preview=False,
                check_reprint=True,
                active_model=self._name,
                active_id=self.id,
                active_ids=self.ids,
            )
        )

    def action_view_check_history(self):
        """Open this payment's immutable check history."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Check History"),
            "res_model": "account.check.print.history",
            "view_mode": "list,form",
            "domain": [("payment_id", "=", self.id)],
            "context": {"create": False, "edit": False, "delete": False},
        }

    def check_layout_values(self):
        """Return current or snapshotted report geometry."""
        self.ensure_one()
        if self.check_layout_snapshot and not self.env.context.get("check_preview"):
            return self.check_layout_snapshot
        return self._layout_snapshot_values()

    def check_field_style(self, field_name):
        """Build absolute CSS from layout data using millimetres only."""
        self.ensure_one()
        layout = self.check_layout_values()
        allowed = self.journal_id.check_layout_id._designer_field_names()
        if field_name not in allowed:
            raise ValidationError(_("Unknown check field: %s", field_name))
        return (
            f"position:absolute;left:{layout[f'{field_name}_x']}mm;"
            f"top:{layout[f'{field_name}_y']}mm;"
            f"width:{layout[f'{field_name}_width']}mm;"
            f"height:{layout[f'{field_name}_height']}mm;"
            f"font-size:{layout['font_size']}pt;overflow:hidden;"
        )

    def get_check_print_amount_words(self):
        """Spell the amount using the journal's configured print language."""
        self.ensure_one()
        lang = "ar_001" if self.journal_id.print_language == "ar" else "en_US"
        return self.currency_id.with_context(lang=lang).amount_to_text(self.amount)

    def check_formatted_amount(self):
        """Format the numeric check amount without an external dependency."""
        self.ensure_one()
        decimals = self.currency_id.decimal_places
        return f"{self.amount:,.{decimals}f}"

    def check_payee_name(self):
        """Return the payment partner or a translated bearer label."""
        self.ensure_one()
        return self.partner_id.name or _("Bearer")
