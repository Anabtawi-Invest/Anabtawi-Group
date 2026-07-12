# -*- coding: utf-8 -*-
"""Shared SOAP response builders for the built-in / standalone MEPS mock gateway."""
import re

NS_SOAP = "http://schemas.xmlsoap.org/soap/envelope/"
NS_TEM = "http://tempuri.org/"
NS_DC = "http://schemas.datacontract.org/2004/07/"

VALID_SCENARIOS = frozenset(
    {"success", "decline", "timeout", "fault", "http500", "bad_xml"}
)

ICP_ENABLE_MOCK = "pos_meps_terminal.enable_mock"


def _escape(value):
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _field(tag, value=None):
    if value is None or value == "":
        return f'<a:{tag} xmlns:a="{NS_DC}"/>'
    return f'<a:{tag} xmlns:a="{NS_DC}">{_escape(value)}</a:{tag}>'


def detect_operation(soap_action, body):
    if soap_action:
        match = re.search(r"IEcrComInterface/(\w+)", soap_action)
        if match:
            return match.group(1)
    text = body.decode("utf-8", errors="replace") if isinstance(body, (bytes, bytearray)) else str(body or "")
    for op in ("Sale", "Void", "Settlement", "Enquiry", "EnquiryByRef"):
        if re.search(rf"<[^:>]*:?{op}[\s>]", text):
            return op
    return "Sale"


def amount_from_body(body):
    text = body.decode("utf-8", errors="replace") if isinstance(body, (bytes, bytearray)) else str(body or "")
    match = re.search(r"EcrAmount[^>]*>([^<]+)<", text)
    return (match.group(1).strip() if match else "0.00") or "0.00"


def success_fields(operation, amount):
    if operation == "Settlement":
        return [
            ("WebResponseStatus", "Success"),
            ("WebResponseErrorDesc", ""),
            ("PosRespStatus", "1"),
            ("PosRespText", "SETTLEMENT OK"),
            ("PosReceipt", "MOCK SETTLEMENT BATCH CLOSED"),
        ]
    return [
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


def decline_fields(operation):
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


def build_result_envelope(operation, fields):
    children = "\n".join(_field(name, value) for name, value in fields)
    xml = f"""<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:soap="{NS_SOAP}">
  <soap:Body>
    <{operation}Response xmlns="{NS_TEM}">
      <{operation}Result>
{children}
      </{operation}Result>
    </{operation}Response>
  </soap:Body>
</soap:Envelope>
"""
    return xml.encode("utf-8")


def build_fault_envelope(message):
    xml = f"""<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:soap="{NS_SOAP}">
  <soap:Body>
    <soap:Fault>
      <faultcode>soap:Server</faultcode>
      <faultstring>{_escape(message)}</faultstring>
    </soap:Fault>
  </soap:Body>
</soap:Envelope>
"""
    return xml.encode("utf-8")


def normalize_scenario(value, default="success"):
    chosen = (value or default or "success").strip().lower()
    return chosen if chosen in VALID_SCENARIOS else "success"


def build_mock_response(scenario, operation, amount, timeout_sleep=12):
    """Return (http_status, content_type, body_bytes, sleep_seconds)."""
    scenario = normalize_scenario(scenario)
    if scenario == "timeout":
        return (
            200,
            "text/xml; charset=utf-8",
            build_result_envelope(operation, success_fields(operation, amount)),
            max(1, int(timeout_sleep)),
        )
    if scenario == "http500":
        return 500, "text/plain; charset=utf-8", b"mock internal error", 0
    if scenario == "bad_xml":
        return 200, "text/plain; charset=utf-8", b"not xml at all", 0
    if scenario == "fault":
        return (
            200,
            "text/xml; charset=utf-8",
            build_fault_envelope(f"Mock SOAP fault for {operation}"),
            0,
        )
    fields = decline_fields(operation) if scenario == "decline" else success_fields(operation, amount)
    return 200, "text/xml; charset=utf-8", build_result_envelope(operation, fields), 0
