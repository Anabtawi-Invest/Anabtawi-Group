from odoo import api, fields, models

# All supported cake sizes (number of persons)
SIZES = [10, 15, 20, 25, 30, 35, 40, 45, 50]

# Weight per 10 persons (kg) — exact from Excel sheet "قالب 10 اشخاص"
WEIGHT_PER_10 = {
    'sponge':      0.49,
    'cream':       0.198,
    'filling':     0.31,
    'decoration':  0.128,
    'sugar_paste': 0.40,
}


class CakeIngredient(models.Model):
    """
    Master data for every selectable ingredient shown as a dropdown in the POS popup.
    Cost per size is auto-calculated using the exact Excel formula:
        cost = cost_per_kg × weight_per_10_persons × (persons / 10)
    Disks use a flat per-unit cost.
    """
    _name = 'cake.ingredient'
    _description = 'Cake Ingredient / Option'
    _order = 'category, sequence, name'

    name         = fields.Char('Name', required=True, translate=True)
    sequence     = fields.Integer('Sequence', default=10)
    active       = fields.Boolean('Active', default=True)
    internal_ref = fields.Char('Internal Reference')

    category = fields.Selection([
        ('sponge',      'سبونج | Sponge'),
        ('cream',       'كريما | Cream'),
        ('filling',     'حشوة | Filling'),
        ('decoration',  'زينة | Decoration'),
        ('disk',        'دسك | Disk'),
        ('sugar_paste', 'عجينة السكر | Sugar Paste'),
    ], required=True, string='Category | الفئة')

    cost_per_kg = fields.Float('Cost / Kg', digits=(10, 5),
                               help='Used for all categories except Disk')
    flat_cost   = fields.Float('Flat Cost / Unit', digits=(10, 5),
                               help='Used only for Disk category')

    # ── Per-size cost columns (mirrors every Excel column) ────────────────────
    cost_10  = fields.Float(compute='_compute_costs', store=True, digits=(10, 4), string='10p')
    cost_15  = fields.Float(compute='_compute_costs', store=True, digits=(10, 4), string='15p')
    cost_20  = fields.Float(compute='_compute_costs', store=True, digits=(10, 4), string='20p')
    cost_25  = fields.Float(compute='_compute_costs', store=True, digits=(10, 4), string='25p')
    cost_30  = fields.Float(compute='_compute_costs', store=True, digits=(10, 4), string='30p')
    cost_35  = fields.Float(compute='_compute_costs', store=True, digits=(10, 4), string='35p')
    cost_40  = fields.Float(compute='_compute_costs', store=True, digits=(10, 4), string='40p')
    cost_45  = fields.Float(compute='_compute_costs', store=True, digits=(10, 4), string='45p')
    cost_50  = fields.Float(compute='_compute_costs', store=True, digits=(10, 4), string='50p')

    @api.depends('cost_per_kg', 'flat_cost', 'category')
    def _compute_costs(self):
        for rec in self:
            for sz in SIZES:
                if rec.category == 'disk':
                    val = rec.flat_cost
                else:
                    w10 = WEIGHT_PER_10.get(rec.category, 0.0)
                    val = rec.cost_per_kg * w10 * (sz / 10.0)
                setattr(rec, f'cost_{sz}', val)

    def get_cost_for_persons(self, persons):
        """Return cost for the nearest supported size."""
        self.ensure_one()
        nearest = min(SIZES, key=lambda x: abs(x - int(persons)))
        return getattr(self, f'cost_{nearest}', 0.0)
