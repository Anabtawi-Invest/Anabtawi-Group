from odoo import _, api, fields, models


class FactoryPlanCategoryOption(models.Model):
    _name = 'factory.plan.category.option'
    _description = 'Factory Plan Category Option'
    _order = 'is_uncategorized, name'
    _rec_name = 'name'

    name = fields.Char(required=True)
    is_uncategorized = fields.Boolean(default=False)

    def name_get(self):
        return [
            (record.id, _('Non') if record.is_uncategorized else record.name)
            for record in self
        ]

    @api.model
    def sync_from_products(self):
        """Ensure selectable options reflect distinct product factory plan categories."""
        Option = self.env['factory.plan.category.option'].sudo()
        if not Option.search([('is_uncategorized', '=', True)], limit=1):
            Option.create({'name': 'Non', 'is_uncategorized': True})

        categories = self.env['product.product'].search([
            ('factory_plan_category', '!=', False),
            ('factory_plan_category', '!=', ''),
        ]).mapped('factory_plan_category')
        existing = set(Option.search([('is_uncategorized', '=', False)]).mapped('name'))
        for category in set(categories):
            if category not in existing:
                Option.create({'name': category})
