# -*- coding: utf-8 -*-

from odoo import _, fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    # Core product fields: declare tracking directly for reliable chatter logs.
    name = fields.Char(tracking=True)
    sale_ok = fields.Boolean(tracking=True)
    purchase_ok = fields.Boolean(tracking=True)
    default_code = fields.Char(tracking=True)
    barcode = fields.Char(tracking=True)
    standard_price = fields.Float(tracking=True)

    @classmethod
    def _setup_complete(cls):
        super()._setup_complete()
        # Optional fields coming from extra apps.
        for field_name in (
            "available_in_pos",
            "has_pledge",
            "branch_allowed",
        ):
            field = cls._fields.get(field_name)
            if field:
                field.tracking = True
        cls._track_get_fields.clear_cache()

    def write(self, vals):
        property_fields = [
            field_name
            for field_name in ("property_account_income_id", "property_account_expense_id")
            if field_name in vals and field_name in self._fields
        ]
        initial_values = {}
        if property_fields:
            for record in self:
                initial_values[record.id] = {field_name: record[field_name] for field_name in property_fields}

        result = super().write(vals)

        if property_fields:
            for record in self:
                messages = []
                for field_name in property_fields:
                    old_value = initial_values[record.id][field_name]
                    new_value = record[field_name]
                    if old_value == new_value:
                        continue
                    label = record._fields[field_name].string
                    old_label = old_value.display_name if old_value else _("Not set")
                    new_label = new_value.display_name if new_value else _("Not set")
                    messages.append(_("%(field)s: %(old)s -> %(new)s", field=label, old=old_label, new=new_label))
                if messages:
                    record.message_post(body="<br/>".join(messages))

        return result
