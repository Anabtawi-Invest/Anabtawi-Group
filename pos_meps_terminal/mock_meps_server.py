#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Local mock for the MEPS / ApexECR SOAP gateway.

Use this when you have no staging terminal. Point Odoo at it:

  Settings → Point of Sale → MEPS Connection → Gateway URL
    http://127.0.0.1:8765/

Any Tid / Mid / Secure Key on the payment method is accepted by default.

Scenarios (pick one):
  ?scenario=success     Approved Sale / Void / Settlement (default)
  ?scenario=decline     Web OK but PosRespStatus != 1
  ?scenario=timeout     Sleep longer than Odoo timeout (blocks the worker)
  ?scenario=fault       SOAP Fault
  ?scenario=http500     HTTP 500 with plain text
  ?scenario=bad_xml     Non-XML body

Or set the same via header:  X-MEPS-Scenario: decline

Examples:
  python3 mock_meps_server.py
  python3 mock_meps_server.py --port 8765 --default-scenario success
  curl -X POST 'http://127.0.0.1:8765/?scenario=decline' \\
       -H 'SOAPAction: http://tempuri.org/IEcrComInterface/Sale' \\
       -H 'Content-Type: text/xml' -d '<xml/>'
"""
from __future__ import annotations

import argparse
import re
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

NS_SOAP = "http://schemas.xmlsoap.org/soap/envelope/"
NS_TEM = "http://tempuri.org/"
NS_DC = "http://schemas.datacontract.org/2004/07/"

VALID_SCENARIOS = frozenset(
    {"success", "decline", "timeout", "fault", "http500", "bad_xml"}
)


def _local(tag: str, value: str | None = None, ns: str = NS_DC) -> str:
    if value is None:
        return f'<a:{tag} xmlns:a="{ns}"/>'
    return f'<a:{tag} xmlns:a="{ns}">{_xml(value)}</a:{tag}>'


def _xml(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _detect_operation(soap_action: str, body: bytes) -> str:
    if soap_action:
        # SOAPAction: "http://tempuri.org/IEcrComInterface/Sale"
        m = re.search(r"IEcrComInterface/(\w+)", soap_action)
        if m:
            return m.group(1)
    text = body.decode("utf-8", errors="replace")
    for op in ("Sale", "Void", "Settlement", "Enquiry", "EnquiryByRef"):
        if f"{op}" in text and ("webReq" in text or f"{op}>" in text or f"{op} " in text):
            # Prefer the first known operation tag that looks like the request root.
            if re.search(rf"<[^:>]*:?{op}[\s>]", text):
                return op
    return "Sale"


def _amount_from_body(body: bytes) -> str:
    text = body.decode("utf-8", errors="replace")
    m = re.search(r"EcrAmount[^>]*>([^<]+)<", text)
    return (m.group(1).strip() if m else "0.00") or "0.00"


def _success_fields(operation: str, amount: str) -> list[tuple[str, str]]:
    common = [
        ("WebResponseStatus", "Success"),
        ("WebResponseErrorDesc", ""),
        ("PosRespStatus", "1"),
        ("PosRespText", "APPROVED"),
        ("PosIssuerName", "Visa"),
        ("PosPan", "************4242"),
        ("PosRRN", "998877665544"),
        ("PosAuthCode", "A1B2C3"),
        ("PosStan", "000042"),
        ("PosCardEntryModeId", "5"),
        ("PosReceipt", f"MOCK {operation} OK\nAMOUNT={amount}\nAPPROVED"),
    ]
    if operation == "Settlement":
        return [
            ("WebResponseStatus", "Success"),
            ("WebResponseErrorDesc", ""),
            ("PosRespStatus", "1"),
            ("PosRespText", "SETTLEMENT OK"),
            ("PosReceipt", "MOCK SETTLEMENT BATCH CLOSED"),
        ]
    return common


def _decline_fields(operation: str) -> list[tuple[str, str]]:
    return [
        ("WebResponseStatus", "Success"),
        ("WebResponseErrorDesc", ""),
        ("PosRespStatus", "0"),
        ("PosRespText", f"MOCK {operation} DECLINED"),
        ("PosIssuerName", "Visa"),
        ("PosPan", "************1111"),
        ("PosRRN", "110011001100"),
        ("PosAuthCode", ""),
        ("PosStan", "000099"),
        ("PosCardEntryModeId", "5"),
    ]


def build_result_envelope(operation: str, fields: list[tuple[str, str]]) -> bytes:
    result_tag = f"{operation}Result"
    response_tag = f"{operation}Response"
    children = "\n".join(_local(name, value) for name, value in fields)
    xml = f"""<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:soap="{NS_SOAP}">
  <soap:Body>
    <{response_tag} xmlns="{NS_TEM}">
      <{result_tag}>
{children}
      </{result_tag}>
    </{response_tag}>
  </soap:Body>
</soap:Envelope>
"""
    return xml.encode("utf-8")


def build_fault_envelope(message: str) -> bytes:
    xml = f"""<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:soap="{NS_SOAP}">
  <soap:Body>
    <soap:Fault>
      <faultcode>soap:Server</faultcode>
      <faultstring>{_xml(message)}</faultstring>
    </soap:Fault>
  </soap:Body>
</soap:Envelope>
"""
    return xml.encode("utf-8")


class MockMepsHandler(BaseHTTPRequestHandler):
    server_version = "MockMeps/1.0"
    default_scenario = "success"
    timeout_sleep = 95

    def log_message(self, fmt: str, *args) -> None:
        print(f"[mock-meps] {self.address_string()} - {fmt % args}")

    def do_GET(self) -> None:
        body = (
            b"MEPS mock gateway is running.\n"
            b"POST SOAP Sale/Void/Settlement here.\n"
            b"Scenarios: success|decline|timeout|fault|http500|bad_xml\n"
            b"Use ?scenario=... or header X-MEPS-Scenario.\n"
        )
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        scenario = self._scenario()
        soap_action = (self.headers.get("SOAPAction") or "").strip().strip('"')
        operation = _detect_operation(soap_action, raw)
        amount = _amount_from_body(raw)

        print(
            f"[mock-meps] op={operation} scenario={scenario} "
            f"amount={amount} action={soap_action!r}"
        )

        if scenario == "timeout":
            print(f"[mock-meps] sleeping {self.timeout_sleep}s to force Odoo timeout…")
            time.sleep(self.timeout_sleep)
            # If Odoo already gave up, writing may fail; ignore.
            try:
                payload = build_result_envelope(
                    operation, _success_fields(operation, amount)
                )
                self._send(200, "text/xml; charset=utf-8", payload)
            except BrokenPipeError:
                pass
            return

        if scenario == "http500":
            self._send(500, "text/plain; charset=utf-8", b"mock internal error")
            return

        if scenario == "bad_xml":
            self._send(200, "text/plain; charset=utf-8", b"not xml at all")
            return

        if scenario == "fault":
            self._send(
                200,
                "text/xml; charset=utf-8",
                build_fault_envelope(f"Mock SOAP fault for {operation}"),
            )
            return

        if scenario == "decline":
            fields = _decline_fields(operation)
        else:
            fields = _success_fields(operation, amount)

        self._send(200, "text/xml; charset=utf-8", build_result_envelope(operation, fields))

    def _scenario(self) -> str:
        query = parse_qs(urlparse(self.path).query)
        from_query = (query.get("scenario") or [None])[0]
        from_header = self.headers.get("X-MEPS-Scenario")
        chosen = (from_query or from_header or self.default_scenario or "success").strip().lower()
        if chosen not in VALID_SCENARIOS:
            print(f"[mock-meps] unknown scenario {chosen!r}, falling back to success")
            return "success"
        return chosen

    def _send(self, status: int, content_type: str, payload: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def main() -> None:
    parser = argparse.ArgumentParser(description="Mock MEPS / ApexECR SOAP gateway")
    parser.add_argument("--host", default="127.0.0.1", help="Bind address (default 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8765, help="Bind port (default 8765)")
    parser.add_argument(
        "--default-scenario",
        default="success",
        choices=sorted(VALID_SCENARIOS),
        help="Scenario when none is requested (default success)",
    )
    parser.add_argument(
        "--timeout-sleep",
        type=int,
        default=95,
        help="Seconds to sleep for scenario=timeout (default 95)",
    )
    args = parser.parse_args()

    MockMepsHandler.default_scenario = args.default_scenario
    MockMepsHandler.timeout_sleep = args.timeout_sleep

    server = ThreadingHTTPServer((args.host, args.port), MockMepsHandler)
    url = f"http://{args.host}:{args.port}/"
    print(f"Mock MEPS listening on {url}")
    print(f"Default scenario: {args.default_scenario}")
    print("In Odoo: Settings → Point of Sale → MEPS Connection → set Gateway URL to that URL")
    print("Per-request override: ?scenario=decline  or  header X-MEPS-Scenario: decline")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.server_close()


if __name__ == "__main__":
    main()
