from odoo import models

class PosSession(models.Model):
    _inherit = "pos.session"

    def _pos_ui_models_to_load(self):
        res = super()._pos_ui_models_to_load()
        return res

    def _loader_params_pos_config(self):
        params = super()._loader_params_pos_config()
        fields = params["search_params"].setdefault("fields", [])
        for f in ("discount_profile_id", "discount_product_id"):
            if f not in fields:
                fields.append(f)
        return params

    def _get_pos_ui_pos_config(self, params):
        data = super()._get_pos_ui_pos_config(params)
        # inject profile buttons as simple array
        for cfg in data:
            cfg["discount_buttons"] = []
            prof = cfg.get("discount_profile_id")
            prof_id = prof[0] if isinstance(prof, list) else prof
            if prof_id:
                profile = self.env["pos.discount.profile"].browse(prof_id)
                cfg["max_fixed_total_discount"] = profile.max_fixed_total
                cfg["discount_buttons"] = [
                    {"id": l.id, "name": l.name, "percent": l.percent}
                    for l in profile.line_ids
                ]
            else:
                cfg["max_fixed_total_discount"] = 0.99
        return data
