from odoo import api, fields, models


class CakeConfig(models.Model):
    """
    Singleton settings record.
    Controls markup %, POS product, manufacturing email, and which extra features are active.
    """
    _name = 'cake.config'
    _description = 'Custom Cake Global Settings'

    name = fields.Char('Config Name', default='Cake Settings', required=True)

    # ── Pricing ───────────────────────────────────────────────────────────────
    markup_pct = fields.Float(
        'Markup % | نسبة الربح',
        default=642.0,
        digits=(6, 2),
        help='Selling price = Total cost × (1 + markup / 100).\n'
             'Default 642% → multiplier ≈ 7.42× which matches the Excel example:\n'
             'basic sales 11.00 ÷ basic cost 1.48 = 7.43×',
    )
    markup_multiplier = fields.Float(
        'Multiplier', compute='_compute_multiplier', store=True, digits=(10, 6),
    )

    @api.depends('markup_pct')
    def _compute_multiplier(self):
        for r in self:
            r.markup_multiplier = 1.0 + r.markup_pct / 100.0

    # ── POS product ───────────────────────────────────────────────────────────
    pos_product_id = fields.Many2one(
        'product.product',
        'POS Product for Custom Cake | منتج POS',
        required=True,
        domain=[('available_in_pos', '=', True)],
        help='A "Service" product available in POS. Its list price is overridden at order time.',
    )

    # ── Email ─────────────────────────────────────────────────────────────────
    manufacturing_email = fields.Char(
        'Manufacturing Team Email | بريد المصنع',
        help='Default To: address when sending cake orders to the production team.',
    )
    email_subject_template = fields.Char(
        'Email Subject Template',
        default='طلب جاتو مخصص #{ref} — Custom Cake Order #{ref}',
        help='Use {ref} for order reference, {persons} for size.',
    )
    auto_send_email = fields.Boolean(
        'Auto-send email after POS payment?',
        default=False,
        help='If enabled, an email is automatically sent to Manufacturing upon payment.',
    )

    # ── Extra features toggle ─────────────────────────────────────────────────
    enable_extra_features = fields.Boolean(
        'Enable Extra Features in POS | تفعيل الإضافات',
        default=True,
        help='Show the extra features section (figures, candles, etc.) in the POS popup.',
    )

    # ══════════════════════════════════════════════════════════════════════════
    # RPC helpers called by POS JavaScript
    # ══════════════════════════════════════════════════════════════════════════

    @api.model
    def get_pos_cake_data(self):
        """
        Single call from POS on session open — returns everything needed by the popup:
        ingredients per category, extra features, config values.
        """
        Ing = self.env['cake.ingredient']
        Feat = self.env['cake.extra.feature']
        cfg = self.search([], limit=1)

        cats = ['sponge', 'cream', 'filling', 'decoration', 'disk', 'sugar_paste']
        ingredients = {}
        for cat in cats:
            recs = Ing.search([('category', '=', cat), ('active', '=', True)],
                              order='sequence, name')
            ingredients[cat] = [{'id': r.id, 'name': r.name} for r in recs]

        extra_features = []
        if cfg and cfg.enable_extra_features:
            feats = Feat.search([('active', '=', True)], order='sequence, name')
            for f in feats:
                feat_data = {
                    'id':           f.id,
                    'name':         f.name,
                    'feature_type': f.feature_type,
                    'extra_cost':   f.extra_cost,
                    'is_size_dependent': f.is_size_dependent,
                    'cost_per_person':   f.cost_per_person,
                    'options': [
                        {'id': o.id, 'name': o.name, 'extra_cost': o.extra_cost}
                        for o in f.option_ids.filtered('active')
                    ],
                }
                extra_features.append(feat_data)

        return {
            'ingredients':        ingredients,
            'extra_features':     extra_features,
            'markup_multiplier':  cfg.markup_multiplier if cfg else 7.43,
            'pos_product_id':     cfg.pos_product_id.id if cfg else False,
            'enable_extra_features': cfg.enable_extra_features if cfg else True,
        }

    @api.model
    def compute_price_rpc(self, persons, sponge_id, cream_id, filling_id,
                          decoration_id, disk_id, use_sugar_paste, sugar_paste_id,
                          extra_selections):
        """
        Called on every change in the POS popup to return an updated selling price.
        extra_selections: list of {feature_id, option_id (or null), text_value (or null)}
        Returns: {total_cost, selling_price}
        """
        Ing = self.env['cake.ingredient']
        Feat = self.env['cake.extra.feature']
        FeatOpt = self.env['cake.extra.feature.option']
        cfg = self.search([], limit=1)

        def ing_cost(ing_id):
            if not ing_id:
                return 0.0
            return Ing.browse(int(ing_id)).get_cost_for_persons(persons)

        total_cost = (
            ing_cost(sponge_id)
            + ing_cost(cream_id)
            + ing_cost(filling_id)
            + ing_cost(decoration_id)
            + ing_cost(disk_id)
            + (ing_cost(sugar_paste_id) if use_sugar_paste and sugar_paste_id else 0.0)
        )

        # Add extra feature costs
        for sel in (extra_selections or []):
            feat = Feat.browse(int(sel.get('feature_id', 0)))
            if not feat.exists():
                continue
            if sel.get('option_id'):
                opt = FeatOpt.browse(int(sel['option_id']))
                if opt.exists() and opt.extra_cost:
                    total_cost += opt.extra_cost
                    continue
            total_cost += feat.get_extra_cost(persons)

        multiplier = cfg.markup_multiplier if cfg else 7.43
        selling_price = round(total_cost * multiplier, 3)
        return {'total_cost': total_cost, 'selling_price': selling_price}

    def compute_selling_price(self, total_cost):
        self.ensure_one()
        return round(total_cost * self.markup_multiplier, 3)
