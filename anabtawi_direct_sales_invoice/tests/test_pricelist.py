from dateutil.relativedelta import relativedelta

from odoo import Command, fields
from odoo.tests import tagged

from .common import DirectSalesCommon


@tagged("post_install", "-at_install")
class TestDirectSalesPricelist(DirectSalesCommon):
    def test_customer_pricelist_currency_and_payment_term_load_automatically(self):
        document = self.make_document()

        self.assertEqual(document.pricelist_id, self.pricelist)
        self.assertEqual(document.currency_id, self.pricelist.currency_id)
        self.assertEqual(document.payment_term_id, self.partner.property_payment_term_id)
        self.assertEqual(document.line_ids.price_unit, 100.0)
        self.assertEqual(document.line_ids.original_pricelist_price, 100.0)

    def test_minimum_quantity_pricing(self):
        self.env["product.pricelist.item"].create(
            {
                "pricelist_id": self.pricelist.id,
                "applied_on": "0_product_variant",
                "product_id": self.product.id,
                "min_quantity": 5.0,
                "compute_price": "fixed",
                "fixed_price": 80.0,
            }
        )

        document = self.make_document(quantity=5.0)

        self.assertEqual(document.line_ids.price_unit, 80.0)

    def test_changing_customer_updates_and_reprices_draft(self):
        replacement = self.env["product.pricelist"].create(
            {
                "name": "Second Customer Pricelist",
                "currency_id": self.company.currency_id.id,
                "company_id": self.company.id,
                "item_ids": [
                    Command.create(
                        {
                            "applied_on": "0_product_variant",
                            "product_id": self.product.id,
                            "compute_price": "fixed",
                            "fixed_price": 55.0,
                        }
                    )
                ],
            }
        )
        self.partner_b.with_company(
            self.company
        ).property_product_pricelist = replacement
        document = self.make_document()

        document.write({"partner_id": self.partner_b.id})

        self.assertEqual(document.pricelist_id, replacement)
        self.assertEqual(document.currency_id, replacement.currency_id)
        self.assertEqual(document.line_ids.price_unit, 55.0)
        self.assertEqual(document.line_ids.original_pricelist_price, 55.0)

    def test_date_validity_is_respected(self):
        today = fields.Date.today()
        self.env["product.pricelist.item"].create(
            {
                "pricelist_id": self.pricelist.id,
                "applied_on": "0_product_variant",
                "product_id": self.product.id,
                "compute_price": "fixed",
                "fixed_price": 65.0,
                "date_start": today - relativedelta(days=1),
                "date_end": today + relativedelta(days=1),
            }
        )
        current = self.make_document(invoice_date=today)
        future = self.make_document(invoice_date=today + relativedelta(days=30))

        self.assertEqual(current.line_ids.price_unit, 65.0)
        self.assertEqual(future.line_ids.price_unit, 100.0)

    def test_pricelist_currency_is_frozen_on_document_and_invoice(self):
        euro = self.env.ref("base.EUR")
        euro.active = True
        euro_pricelist = self.env["product.pricelist"].create(
            {
                "name": "DSI Euro Pricelist",
                "currency_id": euro.id,
                "company_id": self.company.id,
                "item_ids": [
                    Command.create(
                        {
                            "applied_on": "0_product_variant",
                            "product_id": self.product.id,
                            "compute_price": "fixed",
                            "fixed_price": 50.0,
                        }
                    )
                ],
            }
        )
        self.partner.with_company(self.company).property_product_pricelist = euro_pricelist
        document = self.make_document()
        self.company.direct_sales_invoice_creation_policy = "on_warehouse_approval"
        self.submit_and_approve(document)
        replacement = self.env["product.pricelist"].create(
            {
                "name": "Replacement Pricelist",
                "currency_id": self.company.currency_id.id,
                "company_id": self.company.id,
            }
        )
        self.partner.with_company(self.company).property_product_pricelist = replacement

        self.assertEqual(document.pricelist_id, euro_pricelist)
        self.assertEqual(document.currency_id, euro)
        self.assertEqual(document.invoice_id.pricelist_id, euro_pricelist)
        self.assertEqual(document.invoice_id.currency_id, euro)

    def test_customer_invoice_report_does_not_expose_pricelist(self):
        self.company.direct_sales_invoice_creation_policy = "on_warehouse_approval"
        document = self.make_document()
        self.submit_and_approve(document)
        report = self.env.ref("account.account_invoices")

        html, _report_type = report._render_qweb_html(
            report.report_name, document.invoice_id.ids
        )

        self.assertNotIn(self.pricelist.name.encode(), html)
        module_views = self.env["ir.ui.view"].search(
            [
                ("inherit_id", "=", self.env.ref("account.report_invoice_document").id),
                ("key", "=like", "anabtawi_direct_sales_invoice.%"),
            ]
        )
        self.assertFalse(module_views)
