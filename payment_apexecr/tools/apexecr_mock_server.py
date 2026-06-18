#!/usr/bin/env python3
"""
Standalone ApexECR SOAP mock server.

Run:
  python custom_modules/payment_apexecr/tools/apexecr_mock_server.py
  python custom_modules/payment_apexecr/tools/apexecr_mock_server.py --port 18080

Endpoint:
  http://127.0.0.1:18080/apexecrmock

Scenario control:
  Put one of these tags in <ReferenceNumber> to force behavior:
    - ":APPROVE"  => immediate approved
    - ":DECLINE"  => immediate declined
    - ":UNKNOWN"  => first financial response unknown, then EnquiryByRef returns approved
"""

import argparse
import datetime as dt
import random
from http.server import BaseHTTPRequestHandler, HTTPServer
from xml.etree import ElementTree as ET


SCENARIOS = {}


def _text(node, local_name, default=""):
    for elem in node.iter():
        if elem.tag.split("}")[-1] == local_name:
            return (elem.text or "").strip()
    return default


def _set(parent, name, value):
    ET.SubElement(parent, name).text = str(value if value is not None else "")


def _build_financial_response(reference, invoice, approved, unknown=False, txn_name="SALE"):
    rrn = str(random.randint(1, 999999999999)).zfill(12)
    auth = str(random.randint(1, 999999)).zfill(6)
    now = dt.datetime.now()
    root = ET.Element("FinancialTxnResponse")
    _set(root, "WebResponseStatus", "Success")
    _set(root, "WebResponseErrorDesc", "")

    details = ET.SubElement(root, "FinancialTxnResponseDE")
    _set(details, "PosAmount", "10.00")
    _set(details, "PosCurrencyCode", "400")
    _set(details, "PosRRN", rrn if not unknown else "")
    _set(details, "PosAuthCode", auth if not unknown else "")
    _set(details, "PosRespCode", "00" if approved else ("XX" if unknown else "05"))
    _set(details, "PosRespText", "Approved" if approved else ("Unknown" if unknown else "Declined"))
    _set(details, "PosRespStatus", "-1" if unknown else ("1" if approved else "0"))
    _set(details, "PosInvoiceNumber", invoice)
    _set(details, "PosCVMId", "1")
    _set(details, "PosTxnName", txn_name)
    _set(details, "PosBatchNumber", "000001")
    _set(details, "PosStan", str(random.randint(1, 999999)).zfill(6))
    _set(details, "PosDate", now.strftime("%Y%m%d"))
    _set(details, "PosTime", now.strftime("%H%M%S"))

    card = ET.SubElement(details, "CardData")
    _set(card, "PosCardEntryModeId", "5")
    _set(card, "PosIssuerName", "VISA")
    _set(card, "PosPan", "470468******4250")
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _build_enquiry_response(reference):
    scenario = SCENARIOS.get(reference, "approve")
    approved = scenario in {"approve", "unknown_resolved"}
    return _build_financial_response(
        reference=reference,
        invoice="ENQ001",
        approved=approved,
        unknown=False,
        txn_name="ENQUIRY",
    )


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != "/apexecrmock":
            self.send_response(404)
            self.end_headers()
            return

        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        try:
            root = ET.fromstring(raw)
        except ET.ParseError:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"Invalid XML")
            return

        local_root = root.tag.split("}")[-1]
        if local_root == "FinancialTxnRequest":
            reference = _text(root, "ReferenceNumber")
            invoice = _text(root, "InvoiceNumber", "000001")
            txn_name = _text(root, "TransactionType", "SALE").upper()
            ref_upper = (reference or "").upper()
            if ":DECLINE" in ref_upper:
                scenario = "decline"
            elif ":UNKNOWN" in ref_upper:
                scenario = "unknown_then_approved"
            else:
                scenario = "approve"
            SCENARIOS[reference] = "unknown_resolved" if scenario == "unknown_then_approved" else scenario
            payload = _build_financial_response(
                reference=reference,
                invoice=invoice,
                approved=scenario == "approve",
                unknown=scenario == "unknown_then_approved",
                txn_name=txn_name,
            )
            self._reply_xml(payload)
            return

        if local_root == "EnquiryByRefRequest":
            reference = _text(root, "ReferenceNumber")
            payload = _build_enquiry_response(reference)
            self._reply_xml(payload)
            return

        self.send_response(400)
        self.end_headers()
        self.wfile.write(b"Unsupported request type")

    def _reply_xml(self, payload):
        self.send_response(200)
        self.send_header("Content-Type", "text/xml; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, fmt, *args):
        return


def main():
    parser = argparse.ArgumentParser(description="ApexECR SOAP mock server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18080)
    args = parser.parse_args()
    server = HTTPServer((args.host, args.port), Handler)
    print(f"ApexECR mock server listening on http://{args.host}:{args.port}/apexecrmock")
    server.serve_forever()


if __name__ == "__main__":
    main()

