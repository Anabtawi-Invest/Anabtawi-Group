# -*- coding: utf-8 -*-
import logging
from odoo import api, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class PosPredefinedDiscount(models.Model):
    _inherit = 'pos.predefined.discount'

    @api.model
    def pos_get_employee_partners(self, config_id=False, search=False, limit=200):
        """Filter out terminated employees from the POS Employee Discount selection."""
        res = super().pos_get_employee_partners(config_id=config_id, search=search, limit=limit)
        if not res:
            return res

        emp_ids = [r['employee_id'] for r in res if r.get('employee_id')]
        if not emp_ids:
            return res

        terminated_emp_ids = set(
            self.env['hr.employee'].sudo().search([
                ('id', 'in', emp_ids),
                ('profile_employment_status', '=', 'terminated'),
            ]).ids
        )
        if terminated_emp_ids:
            res = [r for r in res if r.get('employee_id') not in terminated_emp_ids]

        return res

    @api.model
    def pos_validate_employee_discount_authorization(self, discount_id, partner_id, password):
        """Prevent applying employee discount if selected employee is terminated."""
        partner = self.env['res.partner'].sudo().browse(int(partner_id or 0)).exists()
        if partner:
            employee = self._employee_for_partner(partner)
            if employee and employee.profile_employment_status == 'terminated':
                _logger.warning(
                    "[pos_predefined_discounts] Attempted employee discount for TERMINATED employee id=%s (%s)",
                    employee.id,
                    employee.name,
                )
                raise UserError(
                    _("Terminated employee '%s' is not eligible for employee discount.") % employee.name
                )

        return super().pos_validate_employee_discount_authorization(discount_id, partner_id, password)
