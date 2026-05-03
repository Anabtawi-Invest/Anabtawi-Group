from odoo import api, fields, models


class SbHrDependent(models.Model):
    _name = "sb.hr.dependent"
    _description = "Employee Dependent"

    employee_id = fields.Many2one("hr.employee", required=True, ondelete="cascade", index=True)
    name = fields.Char(required=True)
    birth_date = fields.Date()
    birth_place = fields.Char()
    medical_insurance = fields.Char(string="Medical Insurance")
    cover = fields.Boolean(string="Covered")


class SbHrWarning(models.Model):
    _name = "sb.hr.warning"
    _description = "Employee Warning"

    employee_id = fields.Many2one("hr.employee", required=True, ondelete="cascade", index=True)
    date = fields.Date(default=fields.Date.context_today)
    warning_type = fields.Selection([
        ("verbal", "Verbal"),
        ("written", "Written"),
        ("final", "Final Warning"),
        ("other", "Other"),
    ], default="written", required=True)
    reason = fields.Text()


class SbHrPreviousJob(models.Model):
    _name = "sb.hr.previous.job"
    _description = "Employee Previous Job"

    employee_id = fields.Many2one("hr.employee", required=True, ondelete="cascade", index=True)
    employer = fields.Char(string="Employer", required=True)
    start_date = fields.Date()
    end_date = fields.Date()
    occupation = fields.Char()
    termination_reason = fields.Char()


class SbHrEducation(models.Model):
    _name = "sb.hr.education"
    _description = "Employee Education"

    employee_id = fields.Many2one("hr.employee", required=True, ondelete="cascade", index=True)
    year = fields.Char()
    degree = fields.Char()
    specialty = fields.Char(string="Specialty")
    institute = fields.Char(string="Institute")


class SbHrOfficialDocument(models.Model):
    _name = "sb.hr.official.document"
    _description = "Employee Official Document"

    employee_id = fields.Many2one("hr.employee", required=True, ondelete="cascade", index=True)
    doc_type = fields.Selection([
        ("national_id", "National ID"),
        ("passport", "Passport"),
        ("driving_license", "Driving License"),
        ("residency", "Residency / Permit"),
        ("other", "Other"),
    ], default="other", required=True)
    number = fields.Char()
    issue_place = fields.Char()
    issue_date = fields.Date()
    expiry_date = fields.Date()


class SbHrCareerMovement(models.Model):
    _name = "sb.hr.career.movement"
    _description = "Employee Career Movement"

    employee_id = fields.Many2one("hr.employee", required=True, ondelete="cascade", index=True)
    movement_type = fields.Selection([
        ("promotion", "Promotion"),
        ("transfer", "Transfer"),
        ("salary_change", "Salary Change"),
        ("title_change", "Title Change"),
        ("other", "Other"),
    ], default="other", required=True)
    date = fields.Date(default=fields.Date.context_today)
    old = fields.Char(string="Old")
    new = fields.Char(string="New")
