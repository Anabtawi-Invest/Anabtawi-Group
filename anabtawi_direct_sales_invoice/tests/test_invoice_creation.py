from odoo.tests import tagged

from .common import DirectSalesCommon


@tagged("post_install", "-at_install")
class TestDirectSalesInvoiceCreation(DirectSalesCommon):
    def test_invoice_copies_customer_quantity_price_tax_terms_and_links(self):
        self.company.direct_sales_invoice_creation_policy = "on_warehouse_approval"
        document = self.make_document(quantity=3.0, payment_term_id=self.pay_terms_b.id)

        self.submit_and_approve(document)

        invoice = document.invoice_id
        invoice_line = invoice.invoice_line_ids.filtered("direct_invoice_line_id")
        self.assertEqual(invoice.move_type, "out_invoice")
        self.assertEqual(invoice.partner_id, self.partner)
        self.assertEqual(invoice_line.quantity, 3.0)
        self.assertEqual(invoice_line.price_unit, document.line_ids.price_unit)
        self.assertEqual(invoice_line.tax_ids, document.line_ids.tax_ids)
        self.assertEqual(invoice.invoice_payment_term_id, self.pay_terms_b)
        self.assertEqual(invoice.direct_sales_invoice_id, document)
        self.assertEqual(document.invoice_id, invoice)
        self.assertEqual(invoice.pickup_warehouse_id, self.warehouse)

    def test_duplicate_invoice_creation_returns_existing_invoice(self):
        self.company.direct_sales_invoice_creation_policy = "on_warehouse_approval"
        document = self.make_document()
        self.submit_and_approve(document)
        original = document.invoice_id

        first_retry = document._create_customer_invoice("approved")
        second_retry = document._create_customer_invoice("approved")

        self.assertEqual(first_retry, original)
        self.assertEqual(second_retry, original)
        self.assertEqual(
            self.env["account.move"].search_count(
                [
                    ("direct_sales_invoice_id", "=", document.id),
                    ("move_type", "=", "out_invoice"),
                    ("state", "!=", "cancel"),
                ]
            ),
            1,
        )

    def test_approval_policy_creates_draft_invoice(self):
        self.company.write(
            {
                "direct_sales_invoice_creation_policy": "on_warehouse_approval",
                "direct_sales_auto_post_invoice": False,
            }
        )
        document = self.make_document()

        self.submit_and_approve(document)

        self.assertEqual(document.invoice_id.state, "draft")

    def test_release_policy_creates_and_auto_posts_invoice(self):
        self.company.write(
            {
                "direct_sales_invoice_creation_policy": "on_goods_release",
                "direct_sales_auto_post_invoice": True,
            }
        )
        document = self.make_document()
        self.submit_and_approve(document)
        document.action_prepare_goods()
        release = document.picking_ids.filtered(
            lambda picking: picking.direct_sales_stage == "release"
        )
        self.mark_picking_quantities_done(release)

        document._confirm_goods_release("Test Customer Representative")

        self.assertEqual(document.invoice_id.state, "posted")
        self.assertEqual(document.state, "completed")
