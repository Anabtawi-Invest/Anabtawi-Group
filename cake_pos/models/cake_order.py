import json
from odoo import api, fields, models


class CakeOrder(models.Model):
    """
    One record per customised cake sold through POS.
    Created automatically after POS payment.
    Triggers a Manufacturing Order and can send an email to production.
    """
    _name = 'cake.order'
    _description = 'Custom Cake Order | طلب جاتو مخصص'
    _order = 'id desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    # ── Identity ──────────────────────────────────────────────────────────────
    name = fields.Char('Reference', readonly=True, default='New', copy=False)
    pos_order_id   = fields.Many2one('pos.order', 'POS Order', readonly=True)
    pos_session_id = fields.Many2one(
        'pos.session', related='pos_order_id.session_id', store=True, readonly=True,
    )
    date_order    = fields.Datetime('Order Date', default=fields.Datetime.now, readonly=True)
    customer_name = fields.Char('Customer Name | اسم الزبون')
    notes         = fields.Text('Special Notes | ملاحظات')

    # ── Cake specification ────────────────────────────────────────────────────
    persons = fields.Selection([
        ('10', '10 أشخاص'), ('15', '15 أشخاص'), ('20', '20 أشخاص'),
        ('25', '25 أشخاص'), ('30', '30 أشخاص'), ('35', '35 أشخاص'),
        ('40', '40 أشخاص'), ('45', '45 أشخاص'), ('50', '50 أشخاص'),
    ], string='Cake Size | حجم القالب', required=True)

    sponge_id     = fields.Many2one('cake.ingredient', 'Sponge | سبونج',
                                    domain=[('category', '=', 'sponge')])
    cream_id      = fields.Many2one('cake.ingredient', 'Cream | كريما',
                                    domain=[('category', '=', 'cream')])
    filling_id    = fields.Many2one('cake.ingredient', 'Filling | حشوة',
                                    domain=[('category', '=', 'filling')])
    decoration_id = fields.Many2one('cake.ingredient', 'Decoration | زينة',
                                    domain=[('category', '=', 'decoration')])
    disk_id       = fields.Many2one('cake.ingredient', 'Disk | دسك',
                                    domain=[('category', '=', 'disk')])
    use_sugar_paste = fields.Boolean('Sugar Paste? | عجينة السكر')
    sugar_paste_id  = fields.Many2one('cake.ingredient', 'Sugar Paste',
                                      domain=[('category', '=', 'sugar_paste')])

    # Extra features stored as JSON (flexible, no schema migration needed)
    extra_features_json    = fields.Text('Extra Features (JSON)', readonly=True)
    extra_features_display = fields.Html(
        'Extra Features', compute='_compute_extra_display', sanitize=False,
    )

    @api.depends('extra_features_json')
    def _compute_extra_display(self):
        for rec in self:
            if not rec.extra_features_json:
                rec.extra_features_display = ''
                continue
            try:
                items = json.loads(rec.extra_features_json)
                rows = ''.join(
                    f'<tr><td><b>{i.get("feature_name", "")}</b></td>'
                    f'<td>{i.get("value", "")}</td></tr>'
                    for i in items
                )
                rec.extra_features_display = (
                    f'<table class="table table-sm table-bordered">{rows}</table>'
                )
            except Exception:
                rec.extra_features_display = rec.extra_features_json

    # ── Pricing (cost hidden from cashier via groups) ──────────────────────────
    total_cost    = fields.Float('Total Cost',    digits=(10, 4),
                                 readonly=True, groups='base.group_system')
    selling_price = fields.Float('Selling Price', digits=(10, 3), readonly=True)

    # ── Status ────────────────────────────────────────────────────────────────
    state = fields.Selection([
        ('new',           'New'),
        ('confirmed',     'Confirmed'),
        ('in_production', 'In Production'),
        ('done',          'Done'),
        ('cancelled',     'Cancelled'),
    ], default='new', tracking=True, string='Status')

    mrp_order_id = fields.Many2one('mrp.production', 'Manufacturing Order', readonly=True)
    email_sent   = fields.Boolean('Email Sent to Manufacturing', readonly=True)

    # ── Sequence ──────────────────────────────────────────────────────────────
    @api.model_create_multi
    def create(self, vals_list):
        seq = self.env['ir.sequence']
        for v in vals_list:
            if v.get('name', 'New') == 'New':
                v['name'] = seq.next_by_code('cake.order') or 'New'
        return super().create(vals_list)

    # ── Spec helpers ──────────────────────────────────────────────────────────
    def _spec_lines(self):
        """Returns list of (label, value) tuples for the full cake spec."""
        self.ensure_one()
        lines = [
            ('Reference | المرجع',         self.name),
            ('Customer | الزبون',           self.customer_name or '—'),
            ('Size | الحجم',               f'{self.persons} أشخاص'),
            ('Sponge | السبونج',            self.sponge_id.name or '—'),
            ('Cream | الكريما',             self.cream_id.name or '—'),
            ('Filling | الحشوة',            self.filling_id.name or '—'),
            ('Decoration | الزينة',         self.decoration_id.name or '—'),
            ('Disk | الدسك',               self.disk_id.name or '—'),
            ('Sugar Paste | عجينة السكر',
             self.sugar_paste_id.name if self.use_sugar_paste else 'No / لا'),
        ]
        if self.extra_features_json:
            try:
                for item in json.loads(self.extra_features_json):
                    lines.append((
                        f'Extra: {item.get("feature_name", "")}',
                        item.get('value', ''),
                    ))
            except Exception:
                pass
        if self.notes:
            lines.append(('Notes | ملاحظات', self.notes))
        return lines

    def _build_html_spec(self):
        """Builds the styled HTML body used in emails and MO notes."""
        rows = ''.join(
            f'<tr>'
            f'<td style="padding:7px 14px;font-weight:600;color:#5a3e00;'
            f'background:#fffdf5;border:1px solid #e8d9a0;">{lbl}</td>'
            f'<td style="padding:7px 14px;border:1px solid #e8d9a0;">{val}</td>'
            f'</tr>'
            for lbl, val in self._spec_lines()
        )
        return (
            '<div style="font-family:Arial,sans-serif;direction:rtl;">'
            '<h2 style="color:#7b3f00;">🎂 طلب جاتو مخصص | Custom Cake Order</h2>'
            f'<table style="border-collapse:collapse;width:100%;">{rows}</table>'
            f'<p style="color:#999;font-size:12px;margin-top:12px;">'
            f'Date: {self.date_order} | Selling Price: {self.selling_price:.3f}'
            f'</p></div>'
        )

    # ── Manufacturing Order ────────────────────────────────────────────────────
    def action_create_mo(self):
        """Creates mrp.production with full cake spec posted as internal note."""
        for rec in self:
            if rec.mrp_order_id:
                continue
            cfg = self.env['cake.config'].search([], limit=1)
            if not cfg or not cfg.pos_product_id:
                continue
            product = cfg.pos_product_id
            mo = self.env['mrp.production'].create({
                'product_id':     product.id,
                'product_qty':    1.0,
                'product_uom_id': product.uom_id.id,
                'origin':         rec.name,
            })
            mo.message_post(
                body=rec._build_html_spec(),
                subject=f'Cake Spec — {rec.name}',
            )
            rec.write({'mrp_order_id': mo.id, 'state': 'confirmed'})

    # ── Email ──────────────────────────────────────────────────────────────────
    def action_send_email(self):
        """Opens the send-email wizard."""
        self.ensure_one()
        return {
            'type':      'ir.actions.act_window',
            'name':      'Send to Manufacturing | إرسال للمصنع',
            'res_model': 'cake.send.email.wizard',
            'view_mode': 'form',
            'target':    'new',
            'context':   {'default_cake_order_id': self.id},
        }

    def _auto_send_email(self):
        """Called automatically after POS payment when auto_send_email is ON."""
        cfg = self.env['cake.config'].search([], limit=1)
        if not cfg or not cfg.manufacturing_email:
            return
        subject = (cfg.email_subject_template or 'Custom Cake Order #{ref}').replace(
            '{ref}', self.name).replace('{persons}', self.persons or '')
        self.env['mail.mail'].sudo().create({
            'subject':   subject,
            'email_to':  cfg.manufacturing_email,
            'body_html': self._build_html_spec(),
        }).send()
        self.write({'email_sent': True})  # [P8] use write(), not direct assignment

    # ── State transitions ──────────────────────────────────────────────────────
    def action_mark_in_production(self):
        self.write({'state': 'in_production'})

    def action_mark_done(self):
        self.write({'state': 'done'})

    def action_cancel(self):
        self.write({'state': 'cancelled'})

    def action_view_mo(self):
        self.ensure_one()
        return {
            'type':      'ir.actions.act_window',
            'name':      'Manufacturing Order',
            'res_model': 'mrp.production',
            'view_mode': 'form',
            'res_id':    self.mrp_order_id.id,
        }
