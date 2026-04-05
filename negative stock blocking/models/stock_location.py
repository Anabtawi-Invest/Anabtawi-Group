from odoo import fields,models
class stocklocation(models.Model):
  _inherit="stock.location"
  restrict_negative=fields.Boolean(
  string="Do NOt Allow Negative stock For This Location",
  help "if this button was True, this location stock will not be negative"
  )
