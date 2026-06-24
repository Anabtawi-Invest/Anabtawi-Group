
from odoo import fields, models
class HrKpiDefinition(models.Model):
    _name='hr.kpi.definition'
    name=fields.Char(required=True)
    code=fields.Char(required=True)
    color=fields.Char(default='#f39c12')
    _sql_constraints=[('hr_kpi_definition_code_unique','unique(code)','KPI code must be unique.')]
