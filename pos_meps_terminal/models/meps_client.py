# -*- coding: utf-8 -*-
"""Low-level SOAP client for the MEPS / ApexECR web service.

Endpoint: https://gprs.mepspay.com/v100/ecrcomInterface.svc
Verified live against the service's own WSDL (2026-07-11): operations are
Sale, Void, PreAuthCompletion, Settlement, RequestCancellation, Enquiry,
EnquiryByRef, SaleQR, CashQR, CashOut. Only Sale/Void/Settlement are wired
up by this module.
"""
import logging

import requests
from lxml import etree

from odoo.exceptions import UserError
from odoo.tools.translate import _

_logger = logging.getLogger(__name__)

# Fallbacks used until a customer overrides them in Settings > Point of Sale > MEPS Connection.
DEFAULT_MEPS_URL = "https://gprs.mepspay.com/v100/ecrcomInterface.svc"
DEFAULT_MEPS_TIMEOUT = 90  # seconds - the call blocks until the physical terminal responds
ICP_ENDPOINT_KEY = "pos_mep_id.endpoint_url"
ICP_TIMEOUT_KEY = "pos_mep_id.timeout"

NS_SOAP = "http://schemas.xmlsoap.org/soap/envelope/"
NS_TEM = "http://tempuri.org/"
NS_DC = "http://schemas.datacontract.org/2004/07/"

_CONFIG_FIELD_ORDER = (
    "EcrCurrencyCode",
    "EcrTillerFullName",
    "EcrTillerUserName",
    "IntegratorName",
    "MerchantSecureKey",
    "Mid",
    "Tenant",
    "Tid",
)
_PRINTER_FIELD_ORDER = (
    "EnablePrintPosReceipt",
    "EnablePrintReceiptNote",
    "InvoiceNumber",
    "PrinterWidth",
    "ReceiptNote",
    "ReferenceNumber",
)
_LOG_BODY_LIMIT = 8000
_REDACT_TAGS = frozenset({"MerchantSecureKey"})


def _clip_log(text):
    text = text or ""
    if len(text) <= _LOG_BODY_LIMIT:
        return text
    return "%s\n... [truncated, %s chars total]" % (text[:_LOG_BODY_LIMIT], len(text))


def _xml_for_log(xml):
    """Pretty-print SOAP XML for logs, with MerchantSecureKey redacted."""
    if xml is None:
        return "(empty)"
    if isinstance(xml, (bytes, bytearray)):
        if not xml:
            return "(empty)"
        try:
            root = etree.fromstring(xml)
        except etree.XMLSyntaxError:
            return _clip_log(xml.decode("utf-8", errors="replace"))
    else:
        root = xml
    clone = etree.fromstring(etree.tostring(root))
    for el in clone.iter():
        if etree.QName(el).localname in _REDACT_TAGS and el.text:
            el.text = "***REDACTED***"
    return _clip_log(etree.tostring(clone, pretty_print=True, encoding="unicode"))


def _dc(tag):
    return f"{{{NS_DC}}}{tag}"


def _sub(parent, tag, value):
    el = etree.SubElement(parent, _dc(tag))
    if value is not None and value != "":
        el.text = str(value)
    return el


def _build_config(values):
    cfg = etree.Element(_dc("Config"))
    for key in _CONFIG_FIELD_ORDER:
        _sub(cfg, key, values.get(key))
    return cfg


def _build_printer(values):
    values = values or {}
    printer = etree.Element(_dc("Printer"))
    for key in _PRINTER_FIELD_ORDER:
        _sub(printer, key, values.get(key))
    return printer


def build_sale_request(config, amount, printer=None):
    sale = etree.Element(f"{{{NS_TEM}}}Sale", nsmap={"tem": NS_TEM})
    web_req = etree.SubElement(sale, f"{{{NS_TEM}}}webReq")
    web_req.append(_build_config(config))
    _sub(web_req, "EcrAmount", f"{float(amount):.2f}")
    web_req.append(_build_printer(printer))
    return sale


def build_void_request(config, orig_auth_code="", orig_invoice_number="", orig_rrn="", printer=None):
    void = etree.Element(f"{{{NS_TEM}}}Void", nsmap={"tem": NS_TEM})
    web_req = etree.SubElement(void, f"{{{NS_TEM}}}webReq")
    web_req.append(_build_config(config))
    _sub(web_req, "OrigAuthCode", orig_auth_code)
    _sub(web_req, "OrigInvoiceNumber", orig_invoice_number)
    _sub(web_req, "OrigRrn", orig_rrn)
    web_req.append(_build_printer(printer))
    return void


def build_settlement_request(config):
    settlement = etree.Element(f"{{{NS_TEM}}}Settlement", nsmap={"tem": NS_TEM})
    web_req = etree.SubElement(settlement, f"{{{NS_TEM}}}webReq")
    web_req.append(_build_config(config))
    return settlement


def _parse_result(content, operation):
    try:
        root = etree.fromstring(content)
    except etree.XMLSyntaxError:
        _logger.error("MEPS %s: could not parse response: %r", operation, content[:2000])
        raise UserError(_("MEPS gateway returned an invalid (non-XML) response."))

    fault = next((el for el in root.iter() if etree.QName(el).localname == "Fault"), None)
    if fault is not None:
        _logger.error("MEPS %s SOAP fault: %s", operation, etree.tostring(fault).decode())
        faultstring = next((el.text for el in fault.iter() if etree.QName(el).localname == "faultstring"), None)
        raise UserError(_("MEPS gateway error: %s") % (faultstring or _("unknown SOAP fault")))

    result_el = next((el for el in root.iter() if etree.QName(el).localname.endswith("Result")), None)
    if result_el is None:
        _logger.error("MEPS %s: no result element in response: %s", operation, etree.tostring(root).decode())
        raise UserError(_("Unexpected MEPS response for %s.") % operation)

    return {etree.QName(child).localname: child.text for child in result_el}


def _get_connection_settings(env):
    ICP = env["ir.config_parameter"].sudo()
    url = ICP.get_param(ICP_ENDPOINT_KEY) or DEFAULT_MEPS_URL
    try:
        timeout = int(ICP.get_param(ICP_TIMEOUT_KEY) or DEFAULT_MEPS_TIMEOUT)
    except ValueError:
        timeout = DEFAULT_MEPS_TIMEOUT
    return url, timeout


def call_meps(env, operation, request_element):
    """POST a single SOAP operation to the MEPS gateway and return the parsed result dict.

    `env` supplies the (customer-configurable) endpoint URL and timeout from
    Settings > Point of Sale > MEPS Connection, falling back to DEFAULT_MEPS_URL/TIMEOUT.

    If the gateway URL points at this module's built-in mock path, the response is
    generated in-process (no HTTP). That is the recommended way to test on Odoo.sh.
    """
    url, timeout = _get_connection_settings(env)

    # In-process mock: avoids Odoo.sh worker self-HTTP deadlocks and needs no tunnel.
    if "/pos_meps_terminal/mock" in (url or ""):
        return _call_meps_mock_inprocess(env, url, operation, request_element, timeout)

    envelope = etree.Element(f"{{{NS_SOAP}}}Envelope", nsmap={"soapenv": NS_SOAP, "tem": NS_TEM})
    etree.SubElement(envelope, f"{{{NS_SOAP}}}Header")
    body = etree.SubElement(envelope, f"{{{NS_SOAP}}}Body")
    body.append(request_element)
    payload = etree.tostring(envelope, xml_declaration=True, encoding="utf-8")

    headers = {
        "Content-Type": "text/xml; charset=utf-8",
        "SOAPAction": f"{NS_TEM}IEcrComInterface/{operation}",
    }

    _logger.info(
        "MEPS %s request: url=%s timeout=%ss SOAPAction=%s\n%s",
        operation,
        url,
        timeout,
        headers["SOAPAction"],
        _xml_for_log(envelope),
    )

    try:
        response = requests.post(url, data=payload, headers=headers, timeout=timeout)
    except requests.exceptions.Timeout:
        _logger.warning(
            "MEPS %s: timed out waiting for terminal response (no response body from %s)",
            operation,
            url,
        )
        raise UserError(_("Timed out waiting for the MEPS terminal to respond."))
    except requests.exceptions.RequestException as exc:
        _logger.exception("MEPS %s: request failed url=%s", operation, url)
        raise UserError(_("Could not reach the MEPS payment gateway: %s") % exc)

    _logger.info(
        "MEPS %s response: url=%s HTTP %s\n%s",
        operation,
        url,
        response.status_code,
        _xml_for_log(response.content),
    )

    if response.status_code != 200:
        raise UserError(_("MEPS gateway returned HTTP %s.") % response.status_code)

    return _parse_result(response.content, operation)


def _call_meps_mock_inprocess(env, url, operation, request_element, timeout):
    from urllib.parse import parse_qs, urlparse

    from odoo.addons.pos_meps_terminal.meps_mock_payload import (
        ICP_ENABLE_MOCK,
        amount_from_body,
        build_mock_response,
        normalize_scenario,
    )

    ICP = env["ir.config_parameter"].sudo()
    if ICP.get_param(ICP_ENABLE_MOCK) != "True":
        raise UserError(_(
            "Built-in MEPS mock URL is configured, but the mock gateway is disabled. "
            "Enable it in Settings → Point of Sale → MEPS Connection."
        ))

    scenario = normalize_scenario((parse_qs(urlparse(url).query).get("scenario") or ["success"])[0])
    amount = amount_from_body(etree.tostring(request_element))
    _logger.info(
        "MEPS in-process mock request: op=%s scenario=%s amount=%s url=%s\n%s",
        operation,
        scenario,
        amount,
        url,
        _xml_for_log(request_element),
    )

    status, _ctype, payload, sleep_s = build_mock_response(
        scenario, operation, amount, timeout_sleep=min(timeout + 2, 15)
    )
    if sleep_s:
        import time
        time.sleep(sleep_s)
        _logger.warning(
            "MEPS in-process mock: timed out waiting for terminal response (no response body from %s)",
            url,
        )
        raise UserError(_("Timed out waiting for the MEPS terminal to respond."))
    _logger.info(
        "MEPS in-process mock response: op=%s HTTP %s\n%s",
        operation,
        status,
        _xml_for_log(payload),
    )
    if status != 200:
        raise UserError(_("MEPS gateway returned HTTP %s.") % status)
    return _parse_result(payload, operation)
