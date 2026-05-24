import logging
import xml.etree.ElementTree as ET

import requests

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


def _build_config_block(pm, user):
    """Return the <Config> XML block common to all Apex requests."""
    return f"""  <Config>
    <Tid>{pm.apex_tid or ''}</Tid>
    <Mid>{pm.apex_mid or ''}</Mid>
    <MerchantSecureKey>{pm.apex_secure_key or ''}</MerchantSecureKey>
    <EcrCurrencyCode>{pm.apex_currency_code or '400'}</EcrCurrencyCode>
    <EcrTillerUserName>{user.login}</EcrTillerUserName>
    <EcrTillerFullName>{user.name}</EcrTillerFullName>
  </Config>"""


def _build_printer_block(pm, invoice_number="", reference_number=""):
    """Return the <Printer> XML block."""
    return f"""  <Printer>
    <PrinterWidth>{pm.apex_printer_width or 40}</PrinterWidth>
    <EnablePrintPosReceipt>{pm.apex_enable_print_pos_receipt or '3'}</EnablePrintPosReceipt>
    <EnablePrintReceiptNote>0</EnablePrintReceiptNote>
    <ReceiptNote></ReceiptNote>
    <InvoiceNumber>{invoice_number}</InvoiceNumber>
    <ReferenceNumber>{reference_number}</ReferenceNumber>
  </Printer>"""


def _post_to_apex(pm, xml_body):
    """POST xml_body to Apex and return the parsed XML root, or raise."""
    timeout = pm.apex_timeout or 90
    resp = requests.post(
        pm.apex_service_url,
        data=xml_body.encode("utf-8"),
        headers={"Content-Type": "text/xml; charset=utf-8"},
        timeout=timeout,
    )
    resp.raise_for_status()
    return ET.fromstring(resp.text)


def _find(root, *tags):
    """Search for any of the given tag names (handles both namespaced
    and plain responses).  Returns the first match's text or ''."""
    for tag in tags:
        # direct child
        el = root.find(f".//{tag}")
        if el is not None:
            return (el.text or "").strip()
    return ""


def _parse_financial_response(root):
    """
    Parse a FinancialTxnResponse.
    The spec wraps most fields inside <FinancialTxnResponseDE>.
    We search the whole tree so both variants work.
    """
    web_status = _find(root, "WebResponseStatus")
    web_error = _find(root, "WebResponseErrorDesc")
    pos_status = _find(root, "PosRespStatus")

    return {
        "success": pos_status == "1",
        "web_status": web_status,
        "web_error": web_error,
        "pos_status": pos_status,
        "resp_code": _find(root, "PosRespCode"),
        "resp_text": _find(root, "PosRespText"),
        "auth_code": _find(root, "PosAuthCode"),
        "rrn": _find(root, "PosRRN"),
        "invoice_number": _find(root, "PosInvoiceNumber"),
        "amount": _find(root, "PosAmount"),
        "currency_code": _find(root, "PosCurrencyCode"),
        "batch_number": _find(root, "PosBatchNumber"),
        "stan": _find(root, "PosStan"),
        "txn_date": _find(root, "PosDate"),
        "txn_time": _find(root, "PosTime"),
        "txn_name": _find(root, "PosTxnName"),
        "cvm_id": _find(root, "PosCVMId"),
        # Card data (nested in <CardData>)
        "card_scheme": _find(root, "PosIssuerName"),
        "masked_pan": _find(root, "PosPan"),
        "card_entry_mode": _find(root, "PosCardEntryModeId"),
        # Receipt
        "receipt": _find(root, "PosReceipt"),
    }


class ApexEcrController(http.Controller):

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _get_payment_method(self, payment_method_id):
        pm = request.env["pos.payment.method"].sudo().browse(payment_method_id)
        if not pm.exists():
            return None, {"success": False, "message": "Payment method not found."}
        if not pm.apex_enabled:
            return None, {"success": False, "message": "Apex ECR is not enabled on this payment method."}
        if not pm.apex_service_url:
            return None, {"success": False, "message": "Apex service URL is not configured."}
        return pm, None

    # ── SALE ─────────────────────────────────────────────────────────────────

    @http.route("/apex_ecr/sale", type="json", auth="user")
    def apex_sale(self, payment_method_id, amount, invoice_number, reference_number=""):
        pm, err = self._get_payment_method(payment_method_id)
        if err:
            return err

        user = request.env.user
        xml_body = f"""<?xml version="1.0" encoding="utf-8"?>
<FinancialTxnRequest
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
  xmlns:xsd="http://www.w3.org/2001/XMLSchema">
{_build_config_block(pm, user)}
{_build_printer_block(pm, invoice_number, reference_number)}
  <TransactionType>SALE</TransactionType>
  <EcrAmount>{amount}</EcrAmount>
  <InvoiceNumber>{invoice_number}</InvoiceNumber>
</FinancialTxnRequest>"""

        try:
            root = _post_to_apex(pm, xml_body)
            return _parse_financial_response(root)
        except Exception as e:
            _logger.exception("Apex SALE request failed")
            return {"success": False, "message": str(e)}

    # ── REFUND ───────────────────────────────────────────────────────────────

    @http.route("/apex_ecr/refund", type="json", auth="user")
    def apex_refund(self, payment_method_id, amount, invoice_number, reference_number=""):
        pm, err = self._get_payment_method(payment_method_id)
        if err:
            return err

        user = request.env.user
        xml_body = f"""<?xml version="1.0" encoding="utf-8"?>
<FinancialTxnRequest
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
  xmlns:xsd="http://www.w3.org/2001/XMLSchema">
{_build_config_block(pm, user)}
{_build_printer_block(pm, invoice_number, reference_number)}
  <TransactionType>REFUND</TransactionType>
  <EcrAmount>{amount}</EcrAmount>
  <InvoiceNumber>{invoice_number}</InvoiceNumber>
</FinancialTxnRequest>"""

        try:
            root = _post_to_apex(pm, xml_body)
            return _parse_financial_response(root)
        except Exception as e:
            _logger.exception("Apex REFUND request failed")
            return {"success": False, "message": str(e)}

    # ── VOID ─────────────────────────────────────────────────────────────────

    @http.route("/apex_ecr/void", type="json", auth="user")
    def apex_void(self, payment_method_id, original_invoice_number):
        """Void a previous transaction by its EFTPOS invoice number."""
        pm, err = self._get_payment_method(payment_method_id)
        if err:
            return err

        user = request.env.user
        xml_body = f"""<?xml version="1.0" encoding="utf-8"?>
<FinancialTxnRequest
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
  xmlns:xsd="http://www.w3.org/2001/XMLSchema">
{_build_config_block(pm, user)}
{_build_printer_block(pm)}
  <TransactionType>VOID</TransactionType>
  <InvoiceNumber>{original_invoice_number}</InvoiceNumber>
</FinancialTxnRequest>"""

        try:
            root = _post_to_apex(pm, xml_body)
            return _parse_financial_response(root)
        except Exception as e:
            _logger.exception("Apex VOID request failed")
            return {"success": False, "message": str(e)}

    # ── CANCEL last request ──────────────────────────────────────────────────

    @http.route("/apex_ecr/cancel", type="json", auth="user")
    def apex_cancel(self, payment_method_id):
        """Send CancelLastRequest to the Apex terminal."""
        pm, err = self._get_payment_method(payment_method_id)
        if err:
            return err

        user = request.env.user
        xml_body = f"""<?xml version="1.0" encoding="utf-8"?>
<CancelRequest
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
  xmlns:xsd="http://www.w3.org/2001/XMLSchema">
{_build_config_block(pm, user)}
</CancelRequest>"""

        try:
            root = _post_to_apex(pm, xml_body)
            web_status = _find(root, "WebResponseStatus")
            web_error = _find(root, "WebResponseErrorDesc")
            return {
                "success": web_status in ("0", "Success"),
                "web_status": web_status,
                "web_error": web_error,
            }
        except Exception as e:
            _logger.exception("Apex CANCEL request failed")
            return {"success": False, "message": str(e)}

    # ── ECR ENQUIRY (recover lost transaction) ───────────────────────────────

    @http.route("/apex_ecr/enquiry", type="json", auth="user")
    def apex_enquiry(self, payment_method_id, orig_invoice_number, orig_rrn="", orig_auth_code=""):
        """
        Recover a transaction that was approved at POS but lost at ECR level.
        Requires the original invoice number and at least one of orig_rrn / orig_auth_code.
        """
        pm, err = self._get_payment_method(payment_method_id)
        if err:
            return err

        user = request.env.user
        xml_body = f"""<?xml version="1.0" encoding="utf-8"?>
<EnquiryRequest
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
  xmlns:xsd="http://www.w3.org/2001/XMLSchema">
{_build_config_block(pm, user)}
{_build_printer_block(pm)}
  <OrigInvoiceNumber>{orig_invoice_number}</OrigInvoiceNumber>
  <OrigRrn>{orig_rrn}</OrigRrn>
  <OrigAuthCode>{orig_auth_code}</OrigAuthCode>
</EnquiryRequest>"""

        try:
            root = _post_to_apex(pm, xml_body)
            return _parse_financial_response(root)
        except Exception as e:
            _logger.exception("Apex ENQUIRY request failed")
            return {"success": False, "message": str(e)}

    # ── Save approved payment data back to pos.payment ───────────────────────

    @http.route("/apex_ecr/save_payment_data", type="json", auth="user")
    def save_payment_data(self, pos_payment_id, apex_data):
        """
        Called by the POS frontend after an approved terminal transaction
        to persist all Apex response fields on the pos.payment record.
        """
        payment = request.env["pos.payment"].sudo().browse(pos_payment_id)
        if not payment.exists():
            return {"success": False, "message": "POS payment record not found."}

        payment.write({
            "apex_rrn": apex_data.get("rrn", ""),
            "apex_auth_code": apex_data.get("auth_code", ""),
            "apex_invoice_number": apex_data.get("invoice_number", ""),
            "apex_resp_code": apex_data.get("resp_code", ""),
            "apex_resp_text": apex_data.get("resp_text", ""),
            "apex_resp_status": apex_data.get("pos_status", ""),
            "apex_card_scheme": apex_data.get("card_scheme", ""),
            "apex_masked_pan": apex_data.get("masked_pan", ""),
            "apex_card_entry_mode": apex_data.get("card_entry_mode", ""),
            "apex_batch_number": apex_data.get("batch_number", ""),
            "apex_stan": apex_data.get("stan", ""),
            "apex_txn_date": apex_data.get("txn_date", ""),
            "apex_txn_time": apex_data.get("txn_time", ""),
            "apex_receipt": apex_data.get("receipt", ""),
        })
        return {"success": True}
