# -*- coding: utf-8 -*-

from odoo import fields, models


class HrAeEmployeeDocument(models.Model):
    _name = "hr.ae.employee.document"
    _description = "Employee document line (HR Enhancement)"
    _order = "employee_id, document_type_id"

    employee_id = fields.Many2one(
        "hr.employee",
        string="Employee",
        required=True,
        ondelete="cascade",
        index=True,
    )
    document_type_id = fields.Many2one(
        "hr.ae.document.type",
        string="Document type",
        required=True,
        ondelete="restrict",
    )
    document_file = fields.Binary(string="File", attachment=True)
    document_filename = fields.Char(string="Filename")
    expiry_date = fields.Date(string="Expires on")
    # Notify stage: 0 = none; 1 = soon (within window); 2 = overdue
    notify_stage = fields.Integer(string="Notify stage", default=0, copy=False)

    _sql_constraints = [
        (
            "hr_ae_employee_document_type_unique",
            "unique(employee_id, document_type_id)",
            "This document type is already attached to the employee.",
        ),
    ]

    def write(self, vals):
        vals = dict(vals or {})
        if "expiry_date" in vals:
            vals["notify_stage"] = 0
        return super().write(vals)
