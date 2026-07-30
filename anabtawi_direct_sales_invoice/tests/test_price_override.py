from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import tagged

from .common import DirectSalesCommon


@tagged("post_install", "-at_install")
class TestDirectSalesPriceOverride(DirectSalesCommon):
    def test_manual_price_requires_reason(self):
        document = self.make_document()

        with self.assertRaisesRegex(ValidationError, "reason is required"):
            document.line_ids.write({"price_unit": 90.0})

    def test_sales_manager_can_approve_audited_override(self):
        document = self.make_document(
            line_values={
                "price_unit": 90.0,
                "price_override_reason": "Approved campaign exception",
            }
        )

        document.action_approve_price_overrides()

        self.assertTrue(document.line_ids.price_overridden)
        self.assertEqual(document.line_ids.price_override_state, "approved")
        self.assertEqual(
            document.line_ids.price_override_approved_by, self.env.user
        )
        self.assertTrue(
            self.env["direct.sales.invoice.approval"].search(
                [
                    ("direct_invoice_id", "=", document.id),
                    ("event", "=", "price_override_approved"),
                ]
            )
        )

    def test_unapproved_override_blocks_submission(self):
        document = self.make_document(
            line_values={
                "price_unit": 90.0,
                "price_override_reason": "Pending commercial decision",
            }
        )

        with self.assertRaisesRegex(UserError, "Sales Manager approval"):
            document.action_submit_to_warehouse()

    def test_user_without_override_group_cannot_change_price(self):
        user = self.env["res.users"].create(
            {
                "name": "Direct Invoice Restricted Salesperson",
                "login": "dsi_restricted_sales",
                "company_id": self.company.id,
                "company_ids": [(6, 0, [self.company.id])],
                "group_ids": [
                    (
                        6,
                        0,
                        [
                            self.env.ref(
                                "anabtawi_direct_sales_invoice.group_direct_invoice_user"
                            ).id
                        ],
                    )
                ],
            }
        )
        user.direct_sales_warehouse_ids = self.warehouse
        document = self.make_document(user_id=user.id)

        with self.assertRaises(AccessError):
            document.line_ids.with_user(user).write(
                {
                    "price_unit": 90.0,
                    "price_override_reason": "Attempted unauthorized override",
                }
            )
