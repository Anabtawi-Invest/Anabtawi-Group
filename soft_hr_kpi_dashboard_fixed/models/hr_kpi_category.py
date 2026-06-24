
from odoo import fields, models
class HrKpiCategory(models.Model):
    _name='hr.kpi.category'
    name=fields.Char(required=True)
    code=fields.Char(required=True)
    _sql_constraints=[('hr_kpi_category_code_unique','unique(code)','Category code must be unique.')]
