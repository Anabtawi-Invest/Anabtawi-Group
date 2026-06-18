# -*- coding: utf-8 -*-

from odoo import api, fields, models


class PosPayment(models.Model):
    _inherit = "pos.payment"

    apexecr_reference_number = fields.Char(string="Apex Reference Number", copy=False, index=True)
    apexecr_invoice_number = fields.Char(string="Apex Invoice Number", copy=False, index=True)
    apexecr_rrn = fields.Char(string="Apex RRN", copy=False, index=True)
    apexecr_auth_code = fields.Char(string="Apex Auth Code", copy=False, index=True)
    apexecr_response_code = fields.Char(string="Apex Response Code", copy=False, index=True)
    apexecr_response_text = fields.Char(string="Apex Response Text", copy=False)
    apexecr_web_status = fields.Char(string="Apex Web Status", copy=False, index=True)
    apexecr_pos_status = fields.Integer(string="Apex POS Status", copy=False, index=True)
    apexecr_transaction_name = fields.Char(string="Apex Transaction Name", copy=False)
    apexecr_masked_pan = fields.Char(string="Apex Masked PAN", copy=False)
    apexecr_raw_response = fields.Text(string="Apex Raw Response", copy=False)
    apexecr_sync_state = fields.Selection(
        selection=[("none", "None"), ("pending", "Pending"), ("done", "Done"), ("error", "Error")],
        string="Apex Reconciliation State",
        default="none",
        copy=False,
        index=True,
    )

    @api.model
    def _load_pos_data_fields(self, config):
        core = [
            "id",
            "uuid",
            "pos_order_id",
            "payment_method_id",
            "amount",
            "payment_date",
            "payment_status",
            "transaction_id",
            "ticket",
            "is_change",
            "card_type",
            "card_brand",
            "card_no",
            "cardholder_name",
            "payment_ref_no",
            "payment_method_authcode",
            "payment_method_issuer_bank",
            "payment_method_payment_mode",
            "write_date",
        ]
        return core + [
            "apexecr_reference_number",
            "apexecr_invoice_number",
            "apexecr_rrn",
            "apexecr_auth_code",
            "apexecr_response_code",
            "apexecr_response_text",
            "apexecr_web_status",
            "apexecr_pos_status",
            "apexecr_transaction_name",
            "apexecr_masked_pan",
            "apexecr_raw_response",
            "apexecr_sync_state",
        ]

    @api.model
    def _cron_apexecr_reconcile_pending(self, limit=100):
        pending_payments = self.search(
            [
                ("payment_method_id.use_payment_terminal", "=", "apexecr"),
                ("apexecr_sync_state", "=", "pending"),
                ("apexecr_reference_number", "!=", False),
            ],
            limit=limit,
            order="id asc",
        )
        for payment in pending_payments:
            try:
                response = self.env["apexecr.client"].enquiry_by_ref(
                    payment.payment_method_id,
                    payment.apexecr_reference_number,
                )
            except Exception:
                payment.apexecr_sync_state = "error"
                continue
            payment._apexecr_apply_normalized_response(response)

    def _apexecr_apply_normalized_response(self, normalized):
        self.ensure_one()
        vals = {
            "apexecr_reference_number": normalized.get("reference_number") or self.apexecr_reference_number,
            "apexecr_invoice_number": normalized.get("invoice_number") or self.apexecr_invoice_number,
            "apexecr_rrn": normalized.get("rrn") or self.apexecr_rrn,
            "apexecr_auth_code": normalized.get("auth_code") or self.apexecr_auth_code,
            "apexecr_response_code": normalized.get("response_code") or "",
            "apexecr_response_text": normalized.get("response_text") or "",
            "apexecr_web_status": normalized.get("web_status"),
            "apexecr_pos_status": normalized.get("pos_status"),
            "apexecr_transaction_name": normalized.get("txn_name"),
            "apexecr_masked_pan": normalized.get("masked_pan") or "",
            "apexecr_raw_response": normalized.get("raw_response"),
            "transaction_id": normalized.get("rrn") or normalized.get("auth_code") or self.transaction_id,
            "payment_method_authcode": normalized.get("auth_code") or self.payment_method_authcode,
            "apexecr_sync_state": normalized.get("sync_state", self.apexecr_sync_state),
        }
        self.write(vals)

