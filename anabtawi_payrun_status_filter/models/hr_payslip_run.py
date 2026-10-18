# -*- coding: utf-8 -*-
from odoo import models


class HrPayslipRun(models.Model):
    _inherit = 'hr.payslip.run'

    EXCLUDED_EMPLOYMENT_STATUSES = ('suspended', 'terminated', 'on_leave')

    def _get_valid_version_ids(self, date_start=None, date_end=None, structure_id=None, company_id=None, employee_ids=None, schedule_pay=None):
        version_ids = super()._get_valid_version_ids(
            date_start=date_start,
            date_end=date_end,
            structure_id=structure_id,
            company_id=company_id,
            employee_ids=employee_ids,
            schedule_pay=schedule_pay,
        )
        if not version_ids:
            return version_ids

        # Filter out contract versions of employees with Suspended, Terminated, or On Leave status
        valid_versions = self.env['hr.version'].browse(version_ids).filtered(
            lambda v: getattr(v.employee_id, 'profile_employment_status', False) not in self.EXCLUDED_EMPLOYMENT_STATUSES
        )
        return valid_versions.ids

    def generate_payslips(self, version_ids=None, employee_ids=None):
        """Ensure that even if version_ids are passed directly, excluded statuses are never generated in the pay run."""
        if version_ids:
            valid_versions = self.env['hr.version'].browse(version_ids).filtered(
                lambda v: getattr(v.employee_id, 'profile_employment_status', False) not in self.EXCLUDED_EMPLOYMENT_STATUSES
            )
            version_ids = valid_versions.ids
        return super().generate_payslips(version_ids=version_ids, employee_ids=employee_ids)
