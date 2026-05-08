# -*- coding: utf-8 -*-
from odoo import fields, models


class HrEmployeeWarningLine(models.Model):
    _name = 'hr.employee.warning.line'
    _description = 'Employee Warning'
    _order = 'warning_date desc, id desc'

    employee_id = fields.Many2one('hr.employee', required=True, ondelete='cascade', index=True)
    warning_date = fields.Date(string='Date', required=True)
    warning_type_id = fields.Many2one('hr.employee.warning.type', string='Warning Type', ondelete='restrict')
    reason = fields.Text(string='Reason')


class HrEmployeeWarningType(models.Model):
    _name = 'hr.employee.warning.type'
    _description = 'Employee Warning Type'
    _order = 'name'

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)


class HrEmployeePreviousJobLine(models.Model):
    _name = 'hr.employee.previous.job.line'
    _description = 'Employee Previous Job'
    _order = 'date_end desc, id desc'

    employee_id = fields.Many2one('hr.employee', required=True, ondelete='cascade', index=True)
    employer = fields.Char(string='Employer')
    date_start = fields.Date(string='Start Date')
    date_end = fields.Date(string='End Date')
    occupation = fields.Char(string='Occupation')
    termination_reason = fields.Char(string='Termination Reason')


class HrEmployeeEducationLine(models.Model):
    _name = 'hr.employee.education.line'
    _description = 'Employee Education'
    _order = 'year desc, id desc'

    employee_id = fields.Many2one('hr.employee', required=True, ondelete='cascade', index=True)
    year = fields.Char(string='Year')
    degree = fields.Char(string='Degree')
    specialty = fields.Char(string='Specialty')
    institute = fields.Char(string='Institute')


class HrEmployeeOfficialDocumentLine(models.Model):
    _name = 'hr.employee.official.document.line'
    _description = 'Employee Official Document'
    _order = 'id'

    employee_id = fields.Many2one('hr.employee', required=True, ondelete='cascade', index=True)
    document_type_id = fields.Many2one('hr.employee.official.document.type', string='Type', ondelete='restrict')
    number = fields.Char(string='Number')
    issue_place = fields.Char(string='Issue Place')
    issue_date = fields.Date(string='Issue Date')
    expiry_date = fields.Date(string='Expiry Date')


class HrEmployeeOfficialDocumentType(models.Model):
    _name = 'hr.employee.official.document.type'
    _description = 'Official Document Type'
    _order = 'name'

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)


class HrEmployeeCareerMovementLine(models.Model):
    _name = 'hr.employee.career.movement.line'
    _description = 'Employee Career Movement'
    _order = 'movement_date desc, id desc'

    employee_id = fields.Many2one('hr.employee', required=True, ondelete='cascade', index=True)
    movement_type_id = fields.Many2one('hr.employee.career.movement.type', string='Type', ondelete='restrict')
    movement_date = fields.Date(string='Date', required=True)
    old_value = fields.Char(string='Old')
    new_value = fields.Char(string='New')


class HrEmployeeCareerMovementType(models.Model):
    _name = 'hr.employee.career.movement.type'
    _description = 'Career Movement Type'
    _order = 'name'

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)
