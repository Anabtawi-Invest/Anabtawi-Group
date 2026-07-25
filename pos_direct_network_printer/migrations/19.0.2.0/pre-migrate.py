"""Remove UI and access metadata from the retired custom printer stack.

The legacy ``printer_printer`` database table is intentionally preserved so
that an administrator can export its branch/printer inventory after upgrading.
"""


def migrate(cr, version):
    model_tables = {
        "ir.ui.view": "ir_ui_view",
        "ir.ui.menu": "ir_ui_menu",
        "ir.actions.act_window": "ir_act_window",
        "ir.rule": "ir_rule",
        "ir.model.access": "ir_model_access",
    }
    legacy_records = (
        ("ir.ui.view", "pos_direct_config_view_form"),
        ("ir.ui.view", "view_pos_printer_form"),
        ("ir.ui.view", "view_printer_printer_tree"),
        ("ir.ui.view", "view_printer_printer_form"),
        ("ir.ui.menu", "menu_printer_printer_config"),
        ("ir.actions.act_window", "action_printer_printer"),
        ("ir.rule", "printer_printer_company_rule"),
        ("ir.model.access", "access_printer_printer_user"),
        ("ir.model.access", "access_printer_printer_manager"),
    )

    for model, name in legacy_records:
        cr.execute(
            """
            SELECT res_id
              FROM ir_model_data
             WHERE module = %s
               AND name = %s
               AND model = %s
            """,
            ("pos_direct_network_printer", name, model),
        )
        result = cr.fetchone()
        if result:
            table = model_tables[model]
            cr.execute(f'DELETE FROM "{table}" WHERE id = %s', (result[0],))
            cr.execute(
                """
                DELETE FROM ir_model_data
                 WHERE module = %s
                   AND name = %s
                   AND model = %s
                """,
                ("pos_direct_network_printer", name, model),
            )
