import odoo

from odoo.addons.point_of_sale.tests.common import TestPoSCommon


@odoo.tests.tagged("post_install", "-at_install")
class TestPosDeliveryAmountReport(TestPoSCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.delivery_journal = cls.env["account.journal"].create(
            {
                "name": "POS Delivery Settlement Journal",
                "code": "PDSL",
                "type": "general",
                "company_id": cls.company.id,
            }
        )
        cls.delivery_intermediate_account = cls.copy_account(
            cls.company_data["default_journal_cash"].default_account_id,
            {"name": "Delivery Intermediate", "code": "PDI200"},
        )
        cls.main_holding_account = cls.copy_account(
            cls.company_data["default_journal_cash"].default_account_id,
            {"name": "Main Holding Cash Fund", "code": "PMH200"},
        )
        cls.difference_account = cls.copy_account(
            cls.company_data["default_journal_cash"].default_account_id,
            {"name": "Branch Cash Surplus Deficit Custody", "code": "PDI201"},
        )

    def setUp(self):
        super().setUp()
        self.config = self.basic_config
        self.config.write(
            {
                "delivery_journal_id": self.delivery_journal.id,
                "delivery_intermediate_account_id": self.delivery_intermediate_account.id,
                "main_holding_cash_fund_account_id": self.main_holding_account.id,
                "delivery_amount_difference_account_id": self.difference_account.id,
            }
        )

    def _prepare_closed_session(self, delivery_amount=100.0):
        session = self.open_new_session(opening_cash=delivery_amount)
        session.post_closing_cash_details(delivery_amount)
        session.update_closing_control_state_session("Close with delivery")
        session.action_process_delivery_amount(delivery_amount)
        session.write({"state": "closed"})
        return session

    def test_generate_reports_and_transfer_matched_amount(self):
        session = self._prepare_closed_session(120.0)
        report_model = self.env["pos.delivery.amount.report"]
        report_model.action_generate_reports()

        line = self.env["pos.delivery.amount.report.line"].search([("session_id", "=", session.id)], limit=1)
        self.assertTrue(line)
        self.assertEqual(line.real_arrived_amount, 120.0)

        line.action_transfer()
        self.assertEqual(line.state, "transferred")
        self.assertTrue(line.settlement_move_id)
        self.assertEqual(line.settlement_move_id.state, "posted")

    def test_transfer_with_difference_posts_difference_line(self):
        session = self._prepare_closed_session(100.0)
        report_model = self.env["pos.delivery.amount.report"]
        report_model.action_generate_reports()

        line = self.env["pos.delivery.amount.report.line"].search([("session_id", "=", session.id)], limit=1)
        line.real_arrived_amount = 70.0
        line.action_transfer()

        self.assertEqual(line.difference, 30.0)
        diff_move_line = line.settlement_move_id.line_ids.filtered(
            lambda l: l.account_id == self.difference_account and l.debit == 30.0
        )
        self.assertTrue(diff_move_line)

    def test_new_draft_line_reopens_report_and_is_editable(self):
        report_model = self.env["pos.delivery.amount.report"]

        first_session = self._prepare_closed_session(80.0)
        report_model.action_generate_reports()
        first_line = self.env["pos.delivery.amount.report.line"].search(
            [("session_id", "=", first_session.id)], limit=1
        )
        first_line.action_transfer()
        self.assertEqual(first_line.report_id.state, "transferred")

        second_session = self._prepare_closed_session(60.0)
        report_model.action_generate_reports()
        second_line = self.env["pos.delivery.amount.report.line"].search(
            [("session_id", "=", second_session.id)], limit=1
        )

        self.assertEqual(second_line.state, "draft")
        self.assertEqual(second_line.report_id, first_line.report_id)
        self.assertEqual(second_line.report_id.state, "draft")

        second_line.real_arrived_amount = 55.0
        self.assertEqual(second_line.real_arrived_amount, 55.0)
