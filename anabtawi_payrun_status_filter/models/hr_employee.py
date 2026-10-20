# -*- coding: utf-8 -*-
import logging
from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.fields import Domain

_logger = logging.getLogger(__name__)


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    def write(self, vals):
        # 1. Detect if profile_employment_status is being set to 'terminated'
        is_terminating = vals.get('profile_employment_status') == 'terminated'

        if is_terminating:
            # Always ensure employee remains active in the Employees module
            vals['active'] = True

            for employee in self:
                # A. Unlink the related user
                if employee.user_id:
                    _logger.info(
                        "[anabtawi_payrun_status_filter] Unlinking user %s (id=%s) from terminated employee %s (id=%s)",
                        employee.user_id.name,
                        employee.user_id.id,
                        employee.name,
                        employee.id,
                    )
                    employee.sudo().user_id = False

                # B. Clear any active OTP password
                if hasattr(employee, 'employee_password') and employee.employee_password:
                    employee.sudo().write({
                        'employee_password': False,
                        'employee_password_generated_at': False,
                        'employee_password_expires_at': False,
                    })

                # C. Close contract/version if any active with a defined start date
                active_versions = getattr(employee, 'version_id', False)
                if active_versions:
                    for v in active_versions.filtered(lambda ver: ver.contract_date_start):
                        update_vals = {}
                        today = fields.Date.today()
                        if not v.contract_date_end or v.contract_date_end > today:
                            update_vals['contract_date_end'] = today
                        if hasattr(v, 'departure_date') and not v.departure_date:
                            update_vals['departure_date'] = today
                        if update_vals:
                            v.sudo().write(update_vals)

        # In case active was attempted to be set to False for an employee with status 'terminated'
        if vals.get('active') is False:
            if any(emp.profile_employment_status == 'terminated' for emp in self):
                vals['active'] = True

        res = super().write(vals)

        # Post-write guarantee: if employee is terminated, ensure active is True
        for employee in self:
            if employee.profile_employment_status == 'terminated' and not employee.active:
                super(HrEmployee, employee.sudo()).write({'active': True})

        return res

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('profile_employment_status') == 'terminated':
                vals['active'] = True
                vals['user_id'] = False
                if 'employee_password' in vals:
                    vals['employee_password'] = False
                    vals['employee_password_generated_at'] = False
                    vals['employee_password_expires_at'] = False

        employees = super().create(vals_list)

        for emp in employees:
            if emp.profile_employment_status == 'terminated':
                if emp.user_id:
                    emp.sudo().user_id = False
                active_versions = getattr(emp, 'version_id', False)
                if active_versions:
                    for v in active_versions.filtered(lambda ver: ver.contract_date_start):
                        today = fields.Date.today()
                        update_vals = {}
                        if not v.contract_date_end or v.contract_date_end > today:
                            update_vals['contract_date_end'] = today
                        if hasattr(v, 'departure_date') and not v.departure_date:
                            update_vals['departure_date'] = today
                        if update_vals:
                            v.sudo().write(update_vals)
        return employees

    # -------------------------------------------------------------
    # OTP / Password Generation Restrictions
    # -------------------------------------------------------------
    def action_generate_employee_portal_otp(self):
        self.ensure_one()
        if self.profile_employment_status == 'terminated':
            raise UserError(_("Cannot generate OTP for terminated employee '%s'.") % self.name)
        return super().action_generate_employee_portal_otp()

    def action_generate_employee_portal_otp_button(self):
        self.ensure_one()
        if self.profile_employment_status == 'terminated':
            raise UserError(_("Cannot generate OTP for terminated employee '%s'.") % self.name)
        return super().action_generate_employee_portal_otp_button()

    # -------------------------------------------------------------
    # Attendance Action Restriction
    # -------------------------------------------------------------
    def _attendance_action_change(self, geo_information=None):
        for employee in self:
            if employee.profile_employment_status == 'terminated':
                raise UserError(_("Cannot perform attendance check in/out for terminated employee '%s'.") % employee.name)
        return super()._attendance_action_change(geo_information=geo_information)

    # -------------------------------------------------------------
    # POS Integration: Cashier loading & Employee Request OTP
    # -------------------------------------------------------------
    @api.model
    def _load_pos_data_domain(self, data, config):
        domain = super()._load_pos_data_domain(data, config)
        return Domain.AND([domain, [('profile_employment_status', '!=', 'terminated')]])

    @api.model
    def pos_employee_request_get_employees(self, config_id=False, search=False, limit=50):
        employees = super().pos_employee_request_get_employees(config_id=config_id, search=search, limit=limit)
        if not employees:
            return employees
        emp_ids = [e['id'] for e in employees if 'id' in e]
        if not emp_ids:
            return employees
        terminated_ids = set(self.sudo().search([
            ('id', 'in', emp_ids),
            ('profile_employment_status', '=', 'terminated')
        ]).ids)
        if terminated_ids:
            employees = [e for e in employees if e.get('id') not in terminated_ids]
        return employees

    @api.model
    def pos_employee_request_password_diag(self, employee_id, password):
        if employee_id:
            emp = self.sudo().browse(int(employee_id)).exists()
            if emp and emp.profile_employment_status == 'terminated':
                return {
                    "ok": False,
                    "reason": "employee_terminated",
                    "employee_id": employee_id,
                }
        return super().pos_employee_request_password_diag(employee_id, password)
