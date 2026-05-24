from odoo import models, fields


class PosPayment(models.Model):
    _inherit = "pos.payment"

    # ── Core approval fields ─────────────────────────────────────────────────
    apex_rrn = fields.Char(string="RRN", readonly=True,
        help="Host Retrieval Reference Number (PosRRN).")
    apex_auth_code = fields.Char(string="Auth Code", readonly=True,
        help="Host Authorization Code (PosAuthCode).")
    apex_invoice_number = fields.Char(string="EFTPOS Invoice No.", readonly=True,
        help="EFTPOS invoice number echoed in PosInvoiceNumber.")
    apex_resp_code = fields.Char(string="Response Code", readonly=True,
        help="2-character host response code (PosRespCode). '00' = approved.")
    apex_resp_text = fields.Char(string="Response Text", readonly=True,
        help="Human-readable response text (PosRespText).")
    apex_resp_status = fields.Char(string="Response Status", readonly=True,
        help="PosRespStatus: 1=Approved, 0=Declined, -1=Unknown.")

    # ── Card data ────────────────────────────────────────────────────────────
    apex_card_scheme = fields.Char(string="Card Scheme", readonly=True,
        help="Card issuer name returned in PosIssuerName (VISA, MASTERCARD…).")
    apex_masked_pan = fields.Char(string="Masked PAN", readonly=True,
        help="PosPan: first 6 and last 4 digits of the card number.")
    apex_card_entry_mode = fields.Char(string="Entry Mode", readonly=True,
        help="PosCardEntryModeId: 1=Manual, 2=Swipe, 3=Chip, 4=Fallback, 5=Contactless, 6=Mobile.")

    # ── Transaction metadata ─────────────────────────────────────────────────
    apex_batch_number = fields.Char(string="Batch No.", readonly=True)
    apex_stan = fields.Char(string="STAN", readonly=True)
    apex_txn_date = fields.Char(string="Txn Date", readonly=True,
        help="Transaction date in yyyyMMdd format.")
    apex_txn_time = fields.Char(string="Txn Time", readonly=True,
        help="Transaction time in HHmmss format.")

    # ── Receipt ──────────────────────────────────────────────────────────────
    apex_receipt = fields.Text(string="EFTPOS Receipt", readonly=True,
        help="Full formatted receipt text returned by the terminal (PosReceipt).")
