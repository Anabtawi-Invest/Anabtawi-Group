from odoo import fields, models


class CakeExtraFeature(models.Model):
    """
    Extra chargeable features the manager can add/remove in the backend.
    Examples: cake figures, candles, custom writing, edible photo print, etc.
    Each feature has a fixed added cost that is applied on top of the ingredient total.
    The cashier sees them as optional checkboxes/dropdowns in the POS popup.
    """
    _name = 'cake.extra.feature'
    _description = 'Custom Cake Extra Feature'
    _order = 'sequence, name'

    name        = fields.Char('Feature Name | اسم الإضافة', required=True, translate=True)
    description = fields.Text('Description | الوصف', translate=True)
    sequence    = fields.Integer('Sequence', default=10)
    active      = fields.Boolean('Active', default=True)

    feature_type = fields.Selection([
        ('checkbox',  'Yes / No (Checkbox)'),
        ('dropdown',  'Choose from list (Dropdown)'),
        ('text',      'Free text (e.g. name on cake)'),
    ], string='Input Type', default='checkbox', required=True,
       help='How the cashier will interact with this feature in the POS popup.')

    # Pricing
    extra_cost  = fields.Float(
        'Extra Cost | التكلفة الإضافية',
        digits=(10, 3),
        help='Added to the total cost when this feature is selected.',
    )
    is_size_dependent = fields.Boolean(
        'Price Varies by Cake Size?',
        help='If checked, use the per-size pricing table below instead of the flat extra_cost.',
    )
    cost_per_person = fields.Float(
        'Extra Cost per Person',
        digits=(10, 3),
        help='Used when "Price Varies by Cake Size" is enabled. '
             'Total extra = cost_per_person × number_of_persons.',
    )

    # Dropdown options (only when feature_type == 'dropdown')
    option_ids = fields.One2many(
        'cake.extra.feature.option', 'feature_id',
        string='Dropdown Options',
    )

    def get_extra_cost(self, persons=0):
        """Return the extra cost for a given cake size."""
        self.ensure_one()
        if self.is_size_dependent:
            return self.cost_per_person * int(persons)
        return self.extra_cost


class CakeExtraFeatureOption(models.Model):
    """
    Individual options for dropdown-type extra features.
    E.g. for "Figures" feature: Cartoon, Bride & Groom, Number, Animal, etc.
    Each option can have its own extra cost override.
    """
    _name = 'cake.extra.feature.option'
    _description = 'Cake Extra Feature Option'
    _order = 'sequence, name'

    feature_id  = fields.Many2one('cake.extra.feature', required=True, ondelete='cascade')
    name        = fields.Char('Option Name', required=True, translate=True)
    sequence    = fields.Integer('Sequence', default=10)
    extra_cost  = fields.Float('Extra Cost Override', digits=(10, 3),
                               help='If set, overrides the parent feature cost for this specific option.')
    active      = fields.Boolean('Active', default=True)
