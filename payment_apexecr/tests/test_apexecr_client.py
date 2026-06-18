# -*- coding: utf-8 -*-

from odoo.tests import common


class TestApexEcrClient(common.SavepointCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.client = cls.env["apexecr.client"]

    def test_sync_state_mapping(self):
        self.assertEqual(self.client._to_sync_state("Success", 1), "done")
        self.assertEqual(self.client._to_sync_state("0", 1), "done")
        self.assertEqual(self.client._to_sync_state("Success", -1), "pending")
        self.assertEqual(self.client._to_sync_state("Success", 0), "error")
        self.assertEqual(self.client._to_sync_state("99", 1), "error")

    def test_parse_financial_response(self):
        xml_payload = """<?xml version="1.0" encoding="utf-8"?>
<FinancialTxnResponse>
  <WebResponseStatus>Success</WebResponseStatus>
  <WebResponseErrorDesc></WebResponseErrorDesc>
  <FinancialTxnResponseDE>
    <PosRRN>123456789012</PosRRN>
    <PosAuthCode>123456</PosAuthCode>
    <PosRespCode>00</PosRespCode>
    <PosRespText>Approved</PosRespText>
    <PosRespStatus>1</PosRespStatus>
    <PosInvoiceNumber>INV001</PosInvoiceNumber>
    <PosTxnName>SALE</PosTxnName>
    <CardData>
      <PosPan>470468******4250</PosPan>
    </CardData>
  </FinancialTxnResponseDE>
</FinancialTxnResponse>
"""
        normalized = self.client._parse_financial_response(xml_payload)
        self.assertTrue(normalized["approved"])
        self.assertEqual(normalized["sync_state"], "done")
        self.assertEqual(normalized["rrn"], "123456789012")
        self.assertEqual(normalized["auth_code"], "123456")
        self.assertEqual(normalized["response_code"], "00")

