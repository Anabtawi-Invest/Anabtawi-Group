# -*- coding: utf-8 -*-

import json
from decimal import Decimal, ROUND_HALF_UP
from urllib import request as urllib_request
from urllib.error import URLError
from xml.etree import ElementTree as ET

from odoo import models
from odoo.exceptions import UserError


class ApexEcrClient(models.AbstractModel):
    _name = "apexecr.client"
    _description = "ApexECR SOAP Client"

    def perform_financial(
        self,
        payment_method,
        transaction_type,
        amount,
        reference_number,
        invoice_number,
        orig_rrn=None,
        orig_auth_code=None,
    ):
        payload = self._build_financial_request_xml(
            payment_method=payment_method,
            transaction_type=transaction_type,
            amount=amount,
            reference_number=reference_number,
            invoice_number=invoice_number,
            orig_rrn=orig_rrn,
            orig_auth_code=orig_auth_code,
        )
        raw_response = self._post_xml(payment_method, payload, operation="FinancialTxn")
        normalized = self._parse_financial_response(raw_response)
        normalized["reference_number"] = reference_number
        return normalized

    def enquiry_by_ref(self, payment_method, reference_number):
        payload = self._build_enquiry_by_ref_request_xml(payment_method, reference_number)
        raw_response = self._post_xml(payment_method, payload, operation="EnquiryByRef")
        normalized = self._parse_enquiry_response(raw_response)
        normalized["reference_number"] = reference_number
        return normalized

    def _build_financial_request_xml(
        self,
        payment_method,
        transaction_type,
        amount,
        reference_number,
        invoice_number,
        orig_rrn=None,
        orig_auth_code=None,
    ):
        root = ET.Element("FinancialTxnRequest")
        root.append(self._build_config_node(payment_method))
        root.append(
            self._build_printer_node(
                payment_method=payment_method,
                invoice_number=invoice_number,
                reference_number=reference_number,
            )
        )
        ET.SubElement(root, "TransactionType").text = transaction_type
        ET.SubElement(root, "EcrAmount").text = self._fmt_amount(amount)
        if orig_rrn:
            ET.SubElement(root, "OrigRrn").text = str(orig_rrn)
        if orig_auth_code:
            ET.SubElement(root, "OrigAuthCode").text = str(orig_auth_code)
        return ET.tostring(root, encoding="utf-8", xml_declaration=True).decode("utf-8")

    def _build_enquiry_by_ref_request_xml(self, payment_method, reference_number):
        root = ET.Element("EnquiryByRefRequest")
        root.append(self._build_config_node(payment_method))
        root.append(
            self._build_printer_node(
                payment_method=payment_method,
                invoice_number="",
                reference_number=reference_number,
            )
        )
        ET.SubElement(root, "ReferenceNumber").text = reference_number
        return ET.tostring(root, encoding="utf-8", xml_declaration=True).decode("utf-8")

    def _build_config_node(self, payment_method):
        config = ET.Element("Config")
        ET.SubElement(config, "Tid").text = payment_method.apexecr_tid or ""
        ET.SubElement(config, "Mid").text = payment_method.apexecr_mid or ""
        ET.SubElement(config, "MerchantSecureKey").text = payment_method.apexecr_merchant_secure_key or ""
        ET.SubElement(config, "EcrCurrencyCode").text = payment_method.apexecr_currency_code or "400"
        ET.SubElement(config, "EcrTillerUserName").text = payment_method.apexecr_tiller_username or ""
        ET.SubElement(config, "EcrTillerFullName").text = payment_method.apexecr_tiller_full_name or ""
        return config

    def _build_printer_node(self, payment_method, invoice_number, reference_number):
        printer = ET.Element("Printer")
        ET.SubElement(printer, "PrinterWidth").text = "40"
        ET.SubElement(printer, "EnablePrintPosReceipt").text = str(
            payment_method.apexecr_enable_print_pos_receipt or 0
        )
        ET.SubElement(printer, "EnablePrintReceiptNote").text = str(
            payment_method.apexecr_enable_print_receipt_note or 0
        )
        ET.SubElement(printer, "ReceiptNote").text = ""
        ET.SubElement(printer, "InvoiceNumber").text = invoice_number or ""
        ET.SubElement(printer, "ReferenceNumber").text = reference_number or ""
        return printer

    def _post_xml(self, payment_method, xml_payload, operation):
        endpoint_url = payment_method.apexecr_endpoint_url
        if not endpoint_url:
            raise UserError("ApexECR endpoint URL is required.")
        timeout_sec = max(5, int(payment_method.apexecr_timeout_sec or 45))
        headers = {"Content-Type": "text/xml; charset=utf-8"}
        body = xml_payload.encode("utf-8")
        req = urllib_request.Request(endpoint_url, data=body, headers=headers, method="POST")
        error_message = None
        response_text = ""
        status = "ok"
        try:
            with urllib_request.urlopen(req, timeout=timeout_sec) as response:
                response_text = response.read().decode("utf-8", errors="replace")
        except URLError as exc:
            status = "error"
            error_message = str(exc)
            raise UserError("ApexECR request failed: %s" % error_message) from exc
        finally:
            self.env["apexecr.log"].sudo().create(
                {
                    "payment_method_id": payment_method.id,
                    "reference_number": self._extract_reference_number(xml_payload),
                    "operation": operation,
                    "request_payload": self._redact_xml(xml_payload),
                    "response_payload": self._redact_xml(response_text),
                    "status": status,
                    "error_message": error_message,
                }
            )
        return response_text

    def _parse_financial_response(self, xml_payload):
        root = ET.fromstring(xml_payload)
        web_status = self._extract_text(root, "WebResponseStatus")
        pos_status = self._extract_int(root, "PosRespStatus")
        response_code = self._extract_text(root, "PosRespCode")
        response_text = self._extract_text(root, "PosRespText")
        rrn = self._extract_text(root, "PosRRN")
        auth_code = self._extract_text(root, "PosAuthCode")
        invoice_number = self._extract_text(root, "PosInvoiceNumber")
        txn_name = self._extract_text(root, "PosTxnName")
        masked_pan = self._extract_text(root, "PosPan")
        status = self._to_sync_state(web_status, pos_status)
        return {
            "web_status": web_status,
            "pos_status": pos_status,
            "response_code": response_code,
            "response_text": response_text,
            "rrn": rrn,
            "auth_code": auth_code,
            "invoice_number": invoice_number,
            "txn_name": txn_name,
            "masked_pan": masked_pan,
            "approved": status == "done",
            "sync_state": status,
            "raw_response": json.dumps({"xml": xml_payload}),
        }

    def _parse_enquiry_response(self, xml_payload):
        parsed = self._parse_financial_response(xml_payload)
        return parsed

    def _extract_text(self, root, local_name):
        for elem in root.iter():
            if elem.tag.split("}")[-1] == local_name:
                return (elem.text or "").strip()
        return ""

    def _extract_int(self, root, local_name):
        txt = self._extract_text(root, local_name)
        if txt == "":
            return None
        try:
            return int(txt)
        except ValueError:
            return None

    def _to_sync_state(self, web_status, pos_status):
        web_success = str(web_status).strip().lower() in {"success", "0"}
        if not web_success:
            return "error"
        if pos_status == 1:
            return "done"
        if pos_status == -1:
            return "pending"
        return "error"

    def _fmt_amount(self, amount):
        amt = Decimal(str(amount or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return f"{amt:.2f}"

    def _extract_reference_number(self, xml_payload):
        try:
            root = ET.fromstring(xml_payload)
        except Exception:
            return ""
        return self._extract_text(root, "ReferenceNumber")

    def _redact_xml(self, xml_payload):
        if not xml_payload:
            return ""
        try:
            root = ET.fromstring(xml_payload)
        except Exception:
            return xml_payload
        sensitive = {"MerchantSecureKey", "PosPanEncrypted", "PosExpDateEncrypted", "PanEncrypted"}
        for elem in root.iter():
            if elem.tag.split("}")[-1] in sensitive and elem.text:
                elem.text = "***REDACTED***"
        return ET.tostring(root, encoding="unicode")

