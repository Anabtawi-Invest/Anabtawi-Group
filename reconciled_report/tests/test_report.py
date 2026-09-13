from unittest.mock import patch

from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestReconciledReport(TransactionCase):
    def test_menu_is_under_payroll_reporting(self):
        menu = self.env.ref('reconciled_report.menu_reconciled_report')
        self.assertTrue(menu.parent_id)
        self.assertEqual(menu.action.res_model, 'reconciled.report.wizard')

    def test_invalid_period(self):
        with self.assertRaises(ValidationError), self.cr.savepoint():
            self.env['reconciled.report.wizard'].create({
                'date_from': '2026-09-30', 'date_to': '2026-09-01',
            })

    def test_empty_selection_is_not_exported(self):
        wizard = self.env['reconciled.report.wizard'].create({
            'date_from': fields.Date.today(), 'date_to': fields.Date.today(),
        })
        with patch.object(type(self.env['hr.payslip']), 'search', return_value=self.env['hr.payslip']):
            with self.assertRaises(UserError):
                wizard.action_export()
