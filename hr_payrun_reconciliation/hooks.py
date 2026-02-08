# -*- coding: utf-8 -*-
from odoo import api, SUPERUSER_ID


def post_init_hook(cr, registry):
    """
    Create the hr.payslip.run form extension view dynamically so we do NOT rely
    on a specific external ID that may differ across Odoo 19 builds.

    This is upgrade-safe and uses only standard ORM APIs.
    """
    env = api.Environment(cr, SUPERUSER_ID, {})

    View = env["ir.ui.view"]
    IMD = env["ir.model.data"]

    # Avoid duplicates if module is reinstalled / updated
    existing = IMD.search([
        ("module", "=", "hr_payrun_reconciliation"),
        ("name", "=", "view_hr_payslip_run_form_inherit_reconciliation_auto"),
        ("model", "=", "ir.ui.view"),
    ], limit=1)
    if existing:
        return

    # Find the main Payslip Run form view actually used in THIS DB.
    # We pick the highest priority "primary" form view for hr.payslip.run.
    base_view = View.search([
        ("model", "=", "hr.payslip.run"),
        ("type", "=", "form"),
        ("mode", "=", "primary"),
        ("active", "=", True),
    ], order="priority desc, id desc", limit=1)

    # If no primary found (rare), fallback to any active form view.
    if not base_view:
        base_view = View.search([
            ("model", "=", "hr.payslip.run"),
            ("type", "=", "form"),
            ("active", "=", True),
        ], order="priority desc, id desc", limit=1)

    if not base_view:
        # Nothing to inherit from => do nothing (keeps install safe)
        return

    arch = """
    <data>
        <xpath expr="//header" position="inside">
            <button name="action_reconciliation"
                    type="object"
                    string="Reconciliation"
                    class="btn-primary"
                    attrs="{'invisible': [('state', '!=', 'draft')], 'readonly': [('reconciliation_done', '=', True)]}"/>
            <button name="action_reset_reconciliation"
                    type="object"
                    string="Reset Reconciliation"
                    class="btn-secondary"
                    attrs="{'invisible': ['|', ('state', '!=', 'draft'), ('reconciliation_done', '=', False)]}"/>
        </xpath>

        <xpath expr="//sheet" position="inside">
            <group>
                <field name="reconciliation_done" invisible="1"/>
            </group>

            <notebook position="inside">
                <page string="Reconciliation Lines" attrs="{'invisible': [('reconciliation_count', '=', 0)]}">
                    <field name="reconciliation_ids" readonly="1" context="{'default_pay_run_id': active_id}">
                        <list>
                            <field name="employee_id"/>
                            <field name="lateness_hours"/>
                            <field name="ot_used_hours"/>
                            <field name="annual_used_hours"/>
                            <field name="late_unpaid_hours"/>
                            <field name="execution_datetime"/>
                            <field name="executed_by"/>
                            <field name="state"/>
                        </list>
                    </field>
                </page>
            </notebook>
        </xpath>
    </data>
    """

    new_view = View.create({
        "name": "hr.payslip.run.form.reconciliation (auto)",
        "type": "form",
        "model": "hr.payslip.run",
        "mode": "extension",
        "inherit_id": base_view.id,
        "priority": 99,
        "arch_db": arch,
    })

    # Create an xmlid for clean uninstall / upgrade tracking
    IMD.create({
        "module": "hr_payrun_reconciliation",
        "name": "view_hr_payslip_run_form_inherit_reconciliation_auto",
        "model": "ir.ui.view",
        "res_id": new_view.id,
        "noupdate": True,
    })
