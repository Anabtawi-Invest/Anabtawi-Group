# -*- coding: utf-8 -*-
from odoo.addons.hr_attendance.controllers.main import HrAttendance
from odoo.fields import Domain
from odoo.http import request
from odoo import _


class HrAttendanceKioskStatusFilter(HrAttendance):

    def employees_infos(self, token, limit, offset, domain):
        """Exclude terminated employees from kiosk manual selection list."""
        filtered_domain = Domain(domain) & Domain([('profile_employment_status', '!=', 'terminated')])
        return super().employees_infos(token, limit, offset, filtered_domain)

    def manual_selection(self, token, employee_id, pin_code, latitude=False, longitude=False):
        """Block attendance check-in/out for terminated employees in kiosk manual selection."""
        employee = request.env['hr.employee'].sudo().browse(int(employee_id or 0)).exists()
        if employee and employee.profile_employment_status == 'terminated':
            return {'warning': _("Cannot record attendance for a terminated employee.")}
        return super().manual_selection(token, employee_id, pin_code, latitude=latitude, longitude=longitude)

    def scan_barcode(self, token, barcode):
        """Block attendance barcode scanning for terminated employees."""
        employee = request.env['hr.employee'].sudo().search([('barcode', '=', barcode)], limit=1)
        if employee and employee.profile_employment_status == 'terminated':
            return {'warning': _("Cannot record attendance for a terminated employee.")}
        return super().scan_barcode(token, barcode)

    def systray_attendance(self, latitude=False, longitude=False):
        """Block systray attendance check-in/out for terminated employees."""
        employee = request.env.user.employee_id
        if employee and employee.profile_employment_status == 'terminated':
            return {'warning': _("Cannot record attendance for a terminated employee.")}
        return super().systray_attendance(latitude=latitude, longitude=longitude)
