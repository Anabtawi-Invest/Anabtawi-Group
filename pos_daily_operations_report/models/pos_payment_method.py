from odoo import _, fields, models
from odoo.exceptions import UserError

PROTECTED_PAYMENT_METHOD_IDS = {142, 143, 144, 145}


class PosPaymentMethod(models.Model):
    _inherit = 'pos.payment.method'

    is_cash = fields.Boolean(
        string='Is Cash',
        help='If enabled, payments using this method are counted in the Cash column of the Daily Operations report.',
    )
    is_hospitality = fields.Boolean(
        string='Is Hospitality',
        help='If enabled, payments using this method are counted in the Hospitality column of the Daily Operations report.',
    )

    def unlink(self):
        protected = self.filtered(lambda method: method.id in PROTECTED_PAYMENT_METHOD_IDS)
        if protected:
            names = ', '.join(protected.mapped('name'))
            raise UserError(
                _('The following payment methods are protected and cannot be deleted: %s') % names
            )
        return super().unlink()
