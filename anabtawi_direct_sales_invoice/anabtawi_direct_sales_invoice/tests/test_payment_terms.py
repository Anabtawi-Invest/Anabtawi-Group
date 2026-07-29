from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import DirectSalesCommon


@tagged("post_install", "-at_install")
class TestDirectSalesPayments(DirectSalesCommon):
    def _approved_invoice(self, payment_term=None, cash=False):
        self.company.direct_sales_invoice_creation_policy = "on_warehouse_approval"
        document = self.make_document(
            payment_term_id=(payment_term or self.pay_terms_a).id,
            is_cash_sale=cash,
        )
        self.submit_and_approve(document)
        document.invoice_id.action_post()
        return document

    def test_immediate_cash_payment_uses_standard_register_payment(self):
        document = self._approved_invoice(cash=True)
        invoice = document.invoice_id
        wizard = (
            self.env["account.payment.register"]
            .with_context(active_model="account.move", active_ids=invoice.ids)
            .create(
                {
                    "journal_id": self.company_data["default_journal_bank"].id,
                    "amount": invoice.amount_residual,
                }
            )
        )

        payments = wizard._create_payments()

        self.assertTrue(payments)
        self.assertEqual(invoice.amount_residual, 0.0)
        self.assertIn(invoice.payment_state, ("in_payment", "paid"))

    def test_credit_invoice_remains_outstanding(self):
        document = self._approved_invoice(payment_term=self.pay_terms_b)

        self.assertFalse(document.is_cash_sale)
        self.assertEqual(document.invoice_id.payment_state, "not_paid")
        self.assertEqual(
            document.invoice_id.amount_residual, document.invoice_id.amount_total
        )

    def test_cash_invoice_creates_one_idempotent_collection_activity(self):
        document = self._approved_invoice(cash=True)
        activity_type = self.env.ref(
            "anabtawi_direct_sales_invoice.mail_activity_direct_payment_collection"
        )

        document._schedule_payment_collection()
        document._schedule_payment_collection()

        activities = document.activity_ids.filtered(
            lambda activity: activity.activity_type_id == activity_type
        )
        self.assertEqual(len(activities), 1)

    def test_payment_terms_generate_maturity_dates(self):
        document = self._approved_invoice(payment_term=self.pay_terms_b)
        receivable_lines = document.invoice_id.line_ids.filtered(
            lambda line: line.account_id.account_type == "asset_receivable"
        )

        self.assertTrue(receivable_lines.mapped("date_maturity"))
        self.assertGreater(
            max(receivable_lines.mapped("date_maturity")),
            document.invoice_id.invoice_date,
        )

    def test_cash_payment_before_release_policy_blocks_unpaid_invoice(self):
        self.company.write(
            {
                "cash_customer_release_policy": "require_payment",
                "direct_sales_invoice_creation_policy": "on_warehouse_approval",
            }
        )
        document = self.make_document(is_cash_sale=True)
        self.submit_and_approve(document)
        document.action_prepare_goods()
        release = document.picking_ids.filtered(
            lambda picking: picking.direct_sales_stage == "release"
        )
        self.mark_picking_quantities_done(release)

        with self.assertRaisesRegex(UserError, "Payment is required"):
            document._confirm_goods_release("Blocked Customer")

        self.assertNotEqual(release.state, "done")

    def test_credit_customer_is_not_blocked_by_cash_policy(self):
        self.company.cash_customer_release_policy = "require_payment"
        document = self.make_document(is_cash_sale=False)
        self.submit_and_approve(document)
        document.action_prepare_goods()
        release = document.picking_ids.filtered(
            lambda picking: picking.direct_sales_stage == "release"
        )
        self.mark_picking_quantities_done(release)

        document._confirm_goods_release("Credit Customer")

        self.assertIn(document.state, ("released", "completed"))
