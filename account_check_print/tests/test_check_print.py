from odoo.tests import new_test_user, tagged
from odoo.exceptions import AccessError, UserError

from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged("post_install", "-at_install")
class TestAccountCheckPrint(AccountTestInvoicingCommon):
    """Exercise numbering, lifecycle, security, and QWeb integration."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.layout = cls.env["account.check.layout"].create({
            "name": "Test Business Check",
            "company_id": cls.env.company.id,
        })
        cls.journal = cls.company_data["default_journal_bank"]
        cls.journal.write({
            "enable_check_printing": True,
            "check_layout_id": cls.layout.id,
            "next_check_number": 1001,
            "print_language": "en",
            "stock_type": "preprinted",
        })
        cls.accounting_user = new_test_user(
            cls.env,
            login="check_accounting_user",
            groups="account.group_account_user",
            company_id=cls.env.company.id,
        )

    def _create_posted_payment(self, amount=125.0):
        """Create one posted outbound vendor payment using the test bank."""
        payment = self.init_payment(-amount, post=False, partner=self.partner_a)
        payment.journal_id = self.journal
        payment.payment_method_line_id = self.outbound_payment_method_line
        payment.action_post()
        return payment

    def test_numbering_and_duplicate_print_protection(self):
        payment = self._create_posted_payment()
        payment.action_print_check()
        self.assertEqual(payment.check_number, "1001")
        self.assertEqual(self.journal.next_check_number, 1002)
        self.assertTrue(payment.printed)
        self.assertEqual(payment.check_history_ids.event_type, "print")
        with self.assertRaises(UserError):
            payment.action_print_check()

    def test_preview_does_not_consume_number(self):
        payment = self._create_posted_payment()
        before = self.journal.next_check_number
        action = payment.with_user(self.accounting_user).action_preview_check()
        self.assertEqual(action["type"], "ir.actions.report")
        self.assertFalse(payment.check_number)
        self.assertEqual(self.journal.next_check_number, before)

    def test_reprint_and_void_are_audited(self):
        payment = self._create_posted_payment()
        payment.action_print_check()
        payment._reprint_check("Printer jam damaged the first copy")
        self.assertEqual(payment.reprinted_count, 1)
        payment._void_check("Vendor bank details changed")
        self.assertTrue(payment.voided)
        self.assertEqual(payment.check_history_count, 3)
        self.assertEqual(
            set(payment.check_history_ids.mapped("event_type")),
            {"print", "reprint", "void"},
        )
        with self.assertRaises(UserError):
            payment._reprint_check("Should fail")

    def test_accounting_user_cannot_print_or_void(self):
        payment = self._create_posted_payment()
        with self.assertRaises(AccessError):
            payment.with_user(self.accounting_user).action_print_check()

    def test_report_html_and_dynamic_paperformat(self):
        payment = self._create_posted_payment()
        payment.action_print_check()
        report = self.env.ref("account_check_print.action_report_check")
        selected = report.with_context(
            active_id=payment.id, active_ids=payment.ids
        ).get_paperformat()
        self.assertEqual(selected, self.layout.paperformat_id)
        html, _report_type = report._render_qweb_html(
            report.report_name, payment.ids, data={}
        )
        self.assertIn(self.partner_a.name.encode(), html)
        self.assertIn(b"1001", html)
