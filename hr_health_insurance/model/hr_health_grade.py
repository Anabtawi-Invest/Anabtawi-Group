# -*- coding: utf-8 -*-

from odoo import fields, models, api, _


class HRHealthGrade(models.Model):
    _name = "hr.health.grade"
    _description = "HR Health Grade"

    name = fields.Char(string='Name')
