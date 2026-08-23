from datetime import timedelta

from odoo import fields
from odoo.addons.point_of_sale.tests.common import CommonPosTest
from odoo.exceptions import ValidationError
from odoo.fields import Command
from odoo.tests import tagged


@tagged("post_install", "-at_install")
class TestOnlineCampaign(CommonPosTest):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.group_ids += (
            cls.env.ref("online_campaigns_discount.group_online_campaign_ecommerce_manager")
            | cls.env.ref("online_campaigns_discount.group_online_campaign_finance_manager")
        )
        cls.category = cls.env["product.category"].create({"name": "Campaign Category"})
        cls.other_category = cls.env["product.category"].create({"name": "Other Category"})
        cls.product = cls.env["product.product"].create({
            "name": "Campaign Product", "list_price": 5.0,
            "available_in_pos": True, "categ_id": cls.category.id,
        })
        cls.other_product = cls.env["product.product"].create({
            "name": "Other Product", "list_price": 4.0,
            "available_in_pos": True, "categ_id": cls.other_category.id,
        })
        cls.pricelist = cls.env["product.pricelist"].create({
            "name": "Aggregator POS Pricelist",
            "currency_id": cls.pos_config_usd.company_id.currency_id.id,
        })
        cls.aggregator = cls.env["online.campaign.aggregator"].create({
            "name": "Test Aggregator",
            "default_commission_percent": 10.0,
            "company_id": cls.pos_config_usd.company_id.id,
            "receivable_account_id": cls.company_data["default_account_receivable"].id,
            "discount_expense_account_id": cls.company_data["default_account_expense"].id,
            "commission_expense_account_id": cls.company_data["default_account_expense"].id,
        })
        cls.now = fields.Datetime.now()
        cls.today = fields.Date.context_today(cls.env.user)
        cls.calendar = cls.env["online.campaign.calendar"].create({
            "name": "Test August Calendar",
            "start_date": cls.today - timedelta(days=1),
            "end_date": cls.today + timedelta(days=30),
            "company_id": cls.pos_config_usd.company_id.id,
        })

    def _campaign(self, **values):
        defaults = {
            "name": "Aggregator 30%",
            "calendar_id": self.calendar.id,
            "start_datetime": self.now - timedelta(days=1),
            "end_datetime": self.now + timedelta(days=30),
            "aggregator_id": self.aggregator.id,
            "discount_percent": 30.0,
            "discount_cap_amount": 10.0,
            "cap_application": "per_line",
            "pricelist_ids": [Command.set(self.pricelist.ids)],
            "apply_scope": "all_products",
            "aggregator_commission_percent": 10.0,
            "aggregator_contribution_percent": 50.0,
            "company_contribution_percent": 50.0,
            "pos_config_ids": [Command.set(self.pos_config_usd.ids)],
            "company_id": self.pos_config_usd.company_id.id,
        }
        defaults.update(values)
        return self.env["online.discount.campaign"].create(defaults)

    def test_01_thirty_percent_with_ten_cap(self):
        campaign = self._campaign()
        self.assertEqual(campaign.compute_discount_amount(50.0, 1), 10.0)
        self.assertEqual(campaign.compute_discount_amount(20.0, 1), 6.0)

    def test_02_contribution_split_and_commission_default(self):
        campaign = self._campaign()
        self.assertEqual(campaign.aggregator_commission_percent, 10.0)
        amount = campaign.compute_discount_amount(15.0, 3)
        self.assertEqual(amount, 4.5)
        self.assertEqual(amount * campaign.aggregator_contribution_percent / 100, 2.25)
        with self.assertRaises(ValidationError):
            campaign.company_contribution_percent = 40

    def test_03_all_product_scope(self):
        campaign = self._campaign()
        self.assertTrue(campaign.applies_to_product(self.product))
        self.assertTrue(campaign.applies_to_product(self.other_product))

    def test_04_specific_product_scope(self):
        campaign = self._campaign(
            apply_scope="specific_products", product_ids=[Command.set(self.product.ids)]
        )
        self.assertTrue(campaign.applies_to_product(self.product))
        self.assertFalse(campaign.applies_to_product(self.other_product))

    def test_05_specific_category_scope(self):
        campaign = self._campaign(
            apply_scope="specific_categories", category_ids=[Command.set(self.category.ids)]
        )
        self.assertTrue(campaign.applies_to_product(self.product))
        self.assertFalse(campaign.applies_to_product(self.other_product))

    def test_06_per_unit_cap(self):
        campaign = self._campaign(discount_percent=50, discount_cap_amount=1, cap_application="per_unit")
        self.assertEqual(campaign.compute_discount_amount(15, 3), 3)

    def test_07_per_line_cap(self):
        campaign = self._campaign(discount_percent=50, discount_cap_amount=4, cap_application="per_line")
        self.assertEqual(campaign.compute_discount_amount(15, 3), 4)

    def test_08_per_order_cap(self):
        campaign = self._campaign(discount_percent=50, discount_cap_amount=5, cap_application="per_order")
        self.assertEqual(campaign.compute_order_discounts([(6, 1), (10, 1), (20, 1)]), [3, 2, 0])

    def test_09_dual_approval_required(self):
        cal = self.env["online.campaign.calendar"].create({
            "name": "Calendar Dual Approval Test",
            "start_date": self.today,
            "end_date": self.today + timedelta(days=10),
            "company_id": self.pos_config_usd.company_id.id,
        })
        campaign = self._campaign(calendar_id=cal.id)
        cal.action_submit()
        self.assertEqual(cal.state, "pending")
        self.assertEqual(campaign.state, "pending")
        cal.action_ecommerce_approve()
        self.assertEqual(cal.state, "pending")
        self.assertEqual(campaign.state, "pending")
        cal.action_finance_approve()
        self.assertEqual(cal.state, "approved")
        self.assertEqual(campaign.state, "approved")
        self.assertTrue(cal.ecommerce_approved)
        self.assertTrue(cal.finance_approved)

    def test_10_unapproved_and_expired_campaigns_not_loaded(self):
        draft_cal = self.env["online.campaign.calendar"].create({
            "name": "Draft Calendar",
            "start_date": self.today,
            "end_date": self.today + timedelta(days=10),
            "company_id": self.pos_config_usd.company_id.id,
        })
        draft = self._campaign(name="Draft", calendar_id=draft_cal.id)

        approved_cal = self.env["online.campaign.calendar"].create({
            "name": "Approved Calendar",
            "start_date": self.today - timedelta(days=10),
            "end_date": self.today - timedelta(days=1),
            "state": "approved",
            "ecommerce_approved": True,
            "finance_approved": True,
            "company_id": self.pos_config_usd.company_id.id,
        })
        expired = self._campaign(
            name="Expired", calendar_id=approved_cal.id, state="approved",
            start_datetime=self.now - timedelta(days=3), end_datetime=self.now - timedelta(days=2),
        )
        domain = draft._load_pos_data_domain({}, self.pos_config_usd)
        loaded = self.env["online.discount.campaign"].search(domain)
        self.assertNotIn(draft, loaded)
        self.assertNotIn(expired, loaded)

    def test_11_backend_receipt_and_commission_values(self):
        campaign = self._campaign(discount_cap_amount=0)
        session = self.env["pos.session"].create({
            "config_id": self.pos_config_usd.id, "user_id": self.env.user.id,
        })
        order = self.env["pos.order"].create({
            "name": "Online Campaign Test", "session_id": session.id,
            "company_id": self.pos_config_usd.company_id.id,
            "amount_tax": 0, "amount_total": 10.5, "amount_paid": 10.5, "amount_return": 0,
            "lines": [Command.create({
                "name": self.product.display_name, "product_id": self.product.id,
                "qty": 3, "price_unit": 5, "discount": 30,
                "price_subtotal": 10.5, "price_subtotal_incl": 10.5,
                "online_campaign_id": campaign.id, "online_aggregator_id": self.aggregator.id,
                "online_discount_percent": 30, "online_discount_amount": 4.5,
                "aggregator_contribution_amount": 2.25, "company_contribution_amount": 2.25,
                "online_discount_cap_amount": 0, "cap_application": "per_line",
                "aggregator_commission_percent": 10, "aggregator_commission_amount": 1.05,
            })],
        })
        self.assertEqual(order.amount_before_online_discount, 15)
        self.assertEqual(order.online_discount_total, 4.5)
        self.assertEqual(order.aggregator_contribution_total, 2.25)
        self.assertEqual(order.company_contribution_total, 2.25)
        self.assertEqual(order.aggregator_commission_total, 1.05)
        self.assertEqual(order.lines.online_customer_paid_amount, 10.5)

    def test_12_jofotara_allowances_are_non_negative(self):
        campaign = self._campaign(discount_cap_amount=0)
        self.assertEqual(campaign.compute_discount_amount(-15.0, -3), 4.5)
        self.assertEqual(campaign.compute_order_discounts([(-15.0, -3)]), [4.5])

    def test_13_profitability_and_settlement_reconciliation(self):
        campaign = self._campaign(discount_cap_amount=0)
        session = self.env["pos.session"].create({
            "config_id": self.pos_config_usd.id, "user_id": self.env.user.id,
        })
        order = self.env["pos.order"].create({
            "name": "Settlement Test", "session_id": session.id,
            "company_id": self.pos_config_usd.company_id.id,
            "state": "paid", "date_order": fields.Datetime.now(),
            "amount_tax": 0, "amount_total": 10.5, "amount_paid": 10.5, "amount_return": 0,
            "lines": [Command.create({
                "name": self.product.display_name, "product_id": self.product.id,
                "qty": 3, "price_unit": 5, "discount": 30,
                "price_subtotal": 10.5, "price_subtotal_incl": 10.5,
                "online_campaign_id": campaign.id, "online_aggregator_id": self.aggregator.id,
                "online_discount_percent": 30, "online_discount_amount": 4.5,
                "aggregator_contribution_amount": 2.25, "company_contribution_amount": 2.25,
                "online_discount_cap_amount": 0, "cap_application": "per_line",
                "aggregator_commission_percent": 10, "aggregator_commission_amount": 1.05,
            })],
        })
        performance = self.env["online.campaign.performance.report"].search([
            ("campaign_id", "=", campaign.id), ("session_id", "=", session.id),
        ])
        self.assertEqual(performance.order_count, 1)
        self.assertAlmostEqual(performance.estimated_net_proceeds, 11.7)
        settlement_move = self.env["account.move"].create({
            "move_type": "entry",
            "journal_id": self.company_data["default_journal_misc"].id,
            "date": fields.Date.context_today(self.env.user),
            "ref": "Online settlement test link",
        })
        settlement = self.env["online.campaign.settlement"].create({
            "aggregator_id": self.aggregator.id,
            "date_start": fields.Date.context_today(self.env.user),
            "date_end": fields.Date.context_today(self.env.user),
            "actual_customer_collections": 10.5,
            "actual_contribution": 2.25,
            "actual_commission": 1.05,
            "statement_reference": "TEST-STMT-001",
            "account_move_id": settlement_move.id,
        })
        settlement.action_confirm()
        self.assertEqual(settlement.order_count, len(order))
        self.assertAlmostEqual(settlement.expected_net_settlement, 11.7)
        self.assertEqual(settlement.variance_amount, 0)
        settlement.action_mark_reconciled()
        self.assertEqual(settlement.state, "reconciled")

    def test_14_post_approval_addition_and_removal(self):
        cal = self.env["online.campaign.calendar"].create({
            "name": "Post Approval Change Calendar",
            "start_date": self.today,
            "end_date": self.today + timedelta(days=30),
            "company_id": self.pos_config_usd.company_id.id,
        })
        existing_campaign = self._campaign(name="Existing Approved Campaign", calendar_id=cal.id)
        cal.action_submit()
        cal.action_ecommerce_approve()
        cal.action_finance_approve()
        self.assertEqual(cal.state, "approved")
        self.assertEqual(existing_campaign.state, "approved")

        # 1. Add a new campaign to the approved calendar -> pending_addition
        new_campaign = self._campaign(name="New Mid-Month Addition", calendar_id=cal.id)
        self.assertEqual(new_campaign.state, "pending_addition")
        self.assertTrue(cal.has_pending_changes)

        # 2. Request removal of existing approved campaign -> pending_removal
        existing_campaign.action_request_removal()
        self.assertEqual(existing_campaign.state, "pending_removal")
        self.assertTrue(cal.has_pending_changes)

        # 3. Dual manager approval for pending changes on the calendar
        cal.action_ecommerce_approve()
        self.assertTrue(cal.pending_ecommerce_approved)
        self.assertEqual(new_campaign.state, "pending_addition") # Awaiting finance
        self.assertEqual(existing_campaign.state, "pending_removal") # Awaiting finance

        cal.action_finance_approve()
        self.assertFalse(cal.has_pending_changes)
        self.assertEqual(new_campaign.state, "approved")
        self.assertEqual(existing_campaign.state, "cancelled")
