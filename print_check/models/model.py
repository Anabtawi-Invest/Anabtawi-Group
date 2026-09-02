from odoo import api, models, fields
from datetime import datetime


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    # جعل حقل رقم الشيك متاحاً للتعديل اليدوي عند الحاجة
    check_number = fields.Char(readonly=False, copy=False)

    def action_print_check(self):
        # if self.payment_method_line_id.payment_method_id.name == 'Checks':
        #     cheque_date = self.date
        # elif self.payment_method_line_id.payment_method_id.name == 'PDC':
        #     cheque_date = self.effective_date
        self.ensure_one()
        partner_name = self.partner_id.name
        return {
            'name': "Print Check",
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'print.check',
            'view_id': self.env.ref('print_check.view_print_check_form').id,
            'target': 'current',
            'context': {
                'default_partner_id': self.partner_id.id,
                'default_partner_name': str(partner_name),
                'default_cheque_amount_in_words': "self-check_amount_in_words",
                'default_cheque_date': self.date,
                'default_cheque_amount': self.amount,
                'default_cheque_memo': self.memo or '',
                'default_payment_id': self.id
            }
        }


class AccountPaymentMethodLine(models.Model):
    _inherit = 'account.payment.method.line'

    @api.constrains('check_next_number')
    def _check_check_next_number(self):
        """تجاوز شرط المنع للسماح بإدخال أي رقم شيك حتى لو كان أصغر من آخر رقم مستخدم"""
        pass

    def _inverse_check_next_number(self):
        """تحديث رقم تسلسل الشيكات في قاعدة البيانات للرقم المدخل فوراً"""
        for line in self:
            if line.check_next_number and line.check_sequence_id:
                try:
                    num = int(line.check_next_number)
                    line.check_sequence_id.sudo().write({'number_next_actual': num})
                except (ValueError, TypeError):
                    pass
        if hasattr(super(), '_inverse_check_next_number'):
            try:
                super()._inverse_check_next_number()
            except Exception:
                pass


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    @api.constrains('check_next_number')
    def _check_next_number(self):
        """تجاوز شرط المنع على مستوى دفتر اليومية"""
        pass

    @api.constrains('check_next_number')
    def _check_check_next_number(self):
        """تجاوز شرط المنع الإضافي على مستوى دفتر اليومية"""
        pass


class PrintCheck(models.TransientModel):
    _name = "print.check"
    _description = "Print Check"

    partner_id = fields.Many2one('res.partner', string='Partner', help='Payee id')

    cheque_amount_in_words = fields.Text(string='Amount in words', help='Cheque Amount in Words')
    cheque_date = fields.Date(string='Date', help='Cheque Date')
    company_id = fields.Many2one('res.company', string="company",
                                 default=lambda self: self.env.company,
                                 help='Company Name')
    currency_id = fields.Many2one('res.currency', string='Currency',
                                  related='company_id.currency_id',
                                  help='Currency')
    cheque_amount = fields.Monetary(currency_field='currency_id',
                                    string='Amount', help='Amount to be paid')
    check_number = fields.Char(string='Check Number', help='Check sequence Number')
    cheque_memo = fields.Char(string='Check memo', help='Check sequence Number')
    payment_id = fields.Many2one('account.payment', string='Payment Type',
                                 help='Payment id')

    def perform_action(self):
        cheque_date = self.cheque_date.strftime("%d/%m/%Y")
