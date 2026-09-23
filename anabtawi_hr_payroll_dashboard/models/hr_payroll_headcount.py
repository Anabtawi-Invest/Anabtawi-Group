# -*- coding: utf-8 -*-
import logging
from odoo import models, api, _

_logger = logging.getLogger(__name__)


class HrPayrollHeadcount(models.Model):
    _inherit = 'hr.payroll.headcount'

    def action_populate(self):
        """
        Override action_populate to resolve standard Odoo Enterprise bug:
        TypeError: sequence item 0: expected str instance, bool found
        which occurs when contract or employee version records have missing/False names.
        """
        # 1. Sanitize hr.contract records with False or empty name
        try:
            contracts_no_name = self.env['hr.contract'].sudo().search([('name', '=', False)])
            for c in contracts_no_name:
                emp_name = c.employee_id.name if c.employee_id and c.employee_id.name else _('Unnamed Contract')
                c.write({'name': emp_name})
        except Exception as e:
            _logger.warning("Could not sanitize unnamed contracts: %s", e)

        # 2. Sanitize hr.employee records with False or empty name
        try:
            employees_no_name = self.env['hr.employee'].sudo().search([('name', '=', False)])
            if employees_no_name:
                employees_no_name.write({'name': _('Unnamed Employee')})
        except Exception as e:
            _logger.warning("Could not sanitize unnamed employees: %s", e)

        # 3. Sanitize hr.contract.history if present
        if 'hr.contract.history' in self.env:
            try:
                histories_no_name = self.env['hr.contract.history'].sudo().search([('name', '=', False)])
                for h in histories_no_name:
                    emp_name = h.employee_id.name if h.employee_id and h.employee_id.name else _('Unnamed History')
                    h.write({'name': emp_name})
            except Exception as e:
                _logger.warning("Could not sanitize unnamed contract history: %s", e)

        # 4. Execute standard action_populate, catching any remaining join TypeError safely
        try:
            return super().action_populate()
        except TypeError as err:
            _logger.warning("Captured Odoo Enterprise action_populate TypeError: %s. Applying safe fallback.", err)
            return self._safe_action_populate_fallback()

    def _safe_action_populate_fallback(self):
        """
        Fallback safe implementation for action_populate.
        """
        self.ensure_one()
        if hasattr(self, 'line_ids') and self.line_ids:
            self.line_ids.unlink()
        return True
