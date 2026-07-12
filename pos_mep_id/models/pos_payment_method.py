# -*- coding: utf-8 -*-
import logging

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools.translate import _

from . import meps_client

_logger = logging.getLogger(__name__)


class PosPaymentMethod(models.Model):
    _inherit = "pos.payment.method"

    meps_enabled = fields.Boolean(
        string="Use MEPS Terminal",
        help="When enabled, selecting this payment method in POS automatically triggers a MEPS card "
        "transaction on the configured terminal instead of a manual/generic payment line.",
    )
    meps_tid = fields.Char(string="MEPS Terminal ID (Tid)")
    meps_mid = fields.Char(string="MEPS Merchant ID (Mid)")
    meps_secure_key = fields.Char(
        string="MEPS Merchant Secure Key",
        groups="point_of_sale.group_pos_manager",
    )
    meps_currency_code = fields.Char(string="MEPS Currency Code", default="400")

    @api.model
    def _load_pos_data_fields(self, config):
        # Only meps_enabled reaches the frontend - Tid/Mid/SecureKey never leave the server.
        fields_to_load = super()._load_pos_data_fields(config)
        if not fields_to_load:
            return fields_to_load
        if "meps_enabled" not in fields_to_load:
            fields_to_load.append("meps_enabled")
        return fields_to_load

    @api.model
    def _meps_get_or_create_journal(self):
        """Shared bank journal used by all MEPS payment methods created via the import wizard."""
        Journal = self.env["account.journal"].sudo()
        journal = Journal.search(
            [("name", "=", "MEPS Terminal"), ("company_id", "=", self.env.company.id)], limit=1
        )
        if journal:
            return journal
        try:
            return Journal.create({
                "name": "MEPS Terminal",
                "type": "bank",
                "code": "MEPS",
                "company_id": self.env.company.id,
            })
        except Exception:
            _logger.exception("MEPS: could not auto-create the 'MEPS Terminal' bank journal; "
                               "set journal_id manually on the payment method(s).")
            return Journal.browse()

    def _meps_check_configured(self):
        self.ensure_one()
        if not (self.meps_tid and self.meps_mid and self.meps_secure_key):
            raise UserError(_("MEPS terminal %s is not fully configured (Tid/Mid/Secure Key).") % self.name)

    def _meps_check_access(self):
        if not self.env.user.has_group("point_of_sale.group_pos_user"):
            raise UserError(_("You are not allowed to trigger MEPS transactions."))

    def _meps_config_values(self):
        self.ensure_one()
        return {
            "Tid": self.meps_tid or "",
            "Mid": self.meps_mid or "",
            "MerchantSecureKey": self.meps_secure_key or "",
            "EcrCurrencyCode": self.meps_currency_code or "400",
            "EcrTillerUserName": (self.env.user.login or "")[:30],
            "EcrTillerFullName": (self.env.user.name or "")[:30],
        }

    def meps_sale(self, amount, invoice_number="", reference_number=""):
        """Perform a MEPS Sale transaction. Blocks until the physical terminal responds."""
        self.ensure_one()
        self._meps_check_access()
        if not self.meps_enabled:
            raise UserError(_("Payment method %s is not configured for MEPS.") % self.name)
        self._meps_check_configured()
        amount = float(amount)
        if amount <= 0:
            raise UserError(_("MEPS sale amount must be greater than zero."))

        request_el = meps_client.build_sale_request(
            self._meps_config_values(),
            amount,
            printer={
                "InvoiceNumber": invoice_number or "",
                "ReferenceNumber": reference_number or "",
            },
        )
        return meps_client.call_meps(self.env, "Sale", request_el)

    def meps_void(self, orig_invoice_number="", orig_rrn="", orig_auth_code=""):
        """Void a previous MEPS Sale by invoice number / RRN / auth code."""
        self.ensure_one()
        self._meps_check_access()
        self._meps_check_configured()

        request_el = meps_client.build_void_request(
            self._meps_config_values(),
            orig_auth_code=orig_auth_code or "",
            orig_invoice_number=orig_invoice_number or "",
            orig_rrn=orig_rrn or "",
        )
        return meps_client.call_meps(self.env, "Void", request_el)

    def meps_settlement(self):
        """Close the EFTPOS batch for this terminal. Irreversible - deletes stored transactions on the terminal."""
        self.ensure_one()
        self._meps_check_access()
        self._meps_check_configured()

        request_el = meps_client.build_settlement_request(self._meps_config_values())
        return meps_client.call_meps(self.env, "Settlement", request_el)

    def meps_settlement_action(self):
        """Backend button wrapper around meps_settlement(): shows the result as a notification."""
        self.ensure_one()
        result = self.meps_settlement()
        success = result.get("WebResponseStatus") == "Success" and result.get("PosRespStatus") == "1"
        message = result.get("PosRespText") or result.get("WebResponseErrorDesc") or _("No response text.")
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("MEPS Settlement") if success else _("MEPS Settlement Failed"),
                "message": message,
                "type": "success" if success else "danger",
                "sticky": not success,
            },
        }
