# models/package_type.py
from odoo import models, fields

class PackingPackageType(models.Model):
    _name = "packing.package.type"
    _description = "Packing Package Type"
    _order = "name"

    name = fields.Char(required=True, translate=True)
    active = fields.Boolean(default=True)
