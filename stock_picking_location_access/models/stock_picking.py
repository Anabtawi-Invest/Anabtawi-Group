from odoo import api, fields, models
from odoo.exceptions import AccessError


class StockPicking(models.Model):
    _inherit = "stock.picking"

    location_access_readonly = fields.Boolean(
        compute="_compute_location_access_readonly",
        help="Technical: current user cannot edit/validate this transfer "
        "because of a From/To location access rule.",
    )
    location_access_warning = fields.Char(
        compute="_compute_location_access_readonly",
    )

    @api.depends("location_id", "location_dest_id", "company_id")
    def _compute_location_access_readonly(self):
        for picking in self:
            rule = picking._get_location_access_rule()
            if not rule:
                picking.location_access_readonly = False
                picking.location_access_warning = False
                continue
            allowed = picking._user_has_location_access(rule)
            picking.location_access_readonly = not allowed
            picking.location_access_warning = (
                False
                if allowed
                else self.env._(
                    "This transfer (%(src)s → %(dest)s) can only be edited or "
                    "approved by: %(users)s. You can view it and print reports only.",
                    src=picking.location_id.display_name,
                    dest=picking.location_dest_id.display_name,
                    users=", ".join(rule.user_ids.mapped("name")),
                )
            )

    def _get_location_access_rule(self):
        """Return the matching active rule for this picking, if any."""
        self.ensure_one()
        if not self.location_id or not self.location_dest_id:
            return self.env["stock.picking.location.access"]
        return self.env["stock.picking.location.access"].sudo().search(
            [
                ("active", "=", True),
                ("company_id", "=", self.company_id.id),
                ("location_id", "=", self.location_id.id),
                ("location_dest_id", "=", self.location_dest_id.id),
            ],
            limit=1,
        )

    def _user_has_location_access(self, rule=None):
        self.ensure_one()
        if self.env.su:
            return True
        rule = rule if rule is not None else self._get_location_access_rule()
        if not rule:
            return True
        # No rule => default Odoo access (no extra restriction).
        return self.env.user in rule.user_ids

    def _check_location_access(self, action_label=None):
        """Raise if current user is not allowed to modify these pickings."""
        if self.env.su or self.env.context.get("skip_stock_picking_location_access"):
            return
        for picking in self:
            rule = picking._get_location_access_rule()
            if not rule:
                # No From/To mapping configured => fallback to default access.
                continue
            if picking._user_has_location_access(rule):
                continue
            action = action_label or self.env._("modify")
            raise AccessError(
                self.env._(
                    "You are not allowed to %(action)s transfer %(name)s "
                    "(%(src)s → %(dest)s).\n"
                    "Only these users can: %(users)s.\n"
                    "You can still view the transfer and download its reports.",
                    action=action,
                    name=picking.display_name,
                    src=picking.location_id.display_name,
                    dest=picking.location_dest_id.display_name,
                    users=", ".join(rule.user_ids.mapped("name")),
                )
            )

    def write(self, vals):
        # Ignore chatter-only / attachment technical writes from report downloads
        ignored = {
            "message_main_attachment_id",
            "website_message_ids",
            "message_ids",
        }
        if set(vals) - ignored:
            self._check_location_access(self.env._("edit"))
        return super().write(vals)

    def unlink(self):
        self._check_location_access(self.env._("delete"))
        return super().unlink()

    def action_confirm(self):
        self._check_location_access(self.env._("confirm"))
        return super().action_confirm()

    def action_assign(self):
        self._check_location_access(self.env._("check availability"))
        return super().action_assign()

    def action_cancel(self):
        self._check_location_access(self.env._("cancel"))
        return super().action_cancel()

    def button_validate(self):
        # Check current pickings first, then allow the validate cascade
        # (push rules creating the next transfer) to proceed.
        self._check_location_access(self.env._("validate / approve"))
        return super(
            StockPicking,
            self.with_context(skip_stock_picking_location_access=True),
        ).button_validate()

    def action_toggle_is_locked(self):
        self._check_location_access(self.env._("lock / unlock"))
        return super().action_toggle_is_locked()

    def do_unreserve(self):
        self._check_location_access(self.env._("unreserve"))
        return super().do_unreserve()
