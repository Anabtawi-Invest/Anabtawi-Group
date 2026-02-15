# -*- coding: utf-8 -*-
from odoo import api, SUPERUSER_ID

VIEW_KEY = 'mass_reconciliation.payslip_list_columns'

ARCH = '''
<data>
    <xpath expr="//tree" position="inside">
        <field name="lateness_hours" optional="show"/>
        <field name="overtime_hours" optional="show"/>
        <field name="remaining_lateness_hours" optional="show"/>
    </xpath>
    <xpath expr="//list" position="inside">
        <field name="lateness_hours" optional="show"/>
        <field name="overtime_hours" optional="show"/>
        <field name="remaining_lateness_hours" optional="show"/>
    </xpath>
    <!-- Remove OT Bank column if present -->
    <xpath expr="//tree/field[@name='ot_bank_hours']" position="replace"/>
    <xpath expr="//list/field[@name='ot_bank_hours']" position="replace"/>
    <xpath expr="//tree/field[@name='ot_bank']" position="replace"/>
    <xpath expr="//list/field[@name='ot_bank']" position="replace"/>
</data>
'''

def post_init_hook(cr, registry):
    env = api.Environment(cr, SUPERUSER_ID, {})
    Views = env['ir.ui.view'].sudo()

    # Try to find a root list/tree view for hr.payslip to inherit (avoid hardcoded xmlid)
    parent = Views.search([
        ('model', '=', 'hr.payslip'),
        ('type', 'in', ('tree', 'list')),
        ('inherit_id', '=', False),
        ('active', '=', True),
    ], order='priority asc, id asc', limit=1)

    if not parent:
        # fallback: any active hr.payslip view
        parent = Views.search([
            ('model', '=', 'hr.payslip'),
            ('type', 'in', ('tree', 'list')),
            ('active', '=', True),
        ], order='inherit_id asc, priority asc, id asc', limit=1)

    if not parent:
        return

    existing = Views.search([('key', '=', VIEW_KEY)], limit=1)
    vals = {
        'name': 'hr.payslip.list.mass.reconciliation.columns',
        'key': VIEW_KEY,
        'type': parent.type,
        'model': 'hr.payslip',
        'inherit_id': parent.id,
        'arch': ARCH,
        'active': True,
        'priority': 90,
    }
    if existing:
        existing.write(vals)
    else:
        Views.create(vals)
