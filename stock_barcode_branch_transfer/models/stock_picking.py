from odoo import fields, models
from odoo.exceptions import UserError


class StockPicking(models.Model):
    _inherit = "stock.picking"

    barcode_locked_source_location_id = fields.Many2one(
        "stock.location",
        string="Locked scanned source",
        copy=False,
        help="First source location scanned in the barcode app for this transfer.",
    )
    barcode_locked_dest_location_id = fields.Many2one(
        "stock.location",
        string="Locked scanned destination",
        copy=False,
        help="First destination location scanned in the barcode app for this transfer.",
    )

    def _get_fields_stock_barcode(self):
        return super()._get_fields_stock_barcode() + [
            "barcode_locked_source_location_id",
            "barcode_locked_dest_location_id",
        ]

    def _branch_location_override_enabled(self):
        self.ensure_one()
        picking_type = self.picking_type_id
        return bool(
            picking_type.barcode_override_scanned_locations
            and picking_type.restrict_scan_source_location == "mandatory"
        )

    def _branch_location_mismatch_message(self, role, location):
        if role == "dest":
            return self.env._(
                "خطأ: الموقع المحدد للوجهة هو %s. لا يُسمح بمسح موقع وجهة آخر.",
                location.display_name,
            )
        return self.env._(
            "خطأ: الموقع المحدد للمصدر هو %s. لا يُسمح بمسح موقع مصدر آخر.",
            location.display_name,
        )

    def _check_branch_scanned_location(self, location):
        self.ensure_one()
        if not location:
            raise UserError(self.env._("خطأ: الموقع الممسوح غير موجود."))
        if self.state in ("done", "cancel"):
            raise UserError(self.env._("خطأ: لا يمكن تغيير مواقع نقل مكتمل أو ملغى."))
        if location.usage not in ("internal", "transit"):
            raise UserError(self.env._("خطأ: الموقع الممسوح غير مسموح به لهذا التحويل."))
        if (
            location.company_id
            and self.company_id
            and location.company_id != self.company_id
        ):
            raise UserError(self.env._("خطأ: الموقع الممسوح لا يتبع نفس الشركة."))

    def _branch_location_payload(self, role):
        self.ensure_one()
        source = self.barcode_locked_source_location_id
        dest = self.barcode_locked_dest_location_id
        return {
            "applied": True,
            "role": role,
            "location_id": self.location_id.id,
            "location_name": self.location_id.display_name,
            "location_dest_id": self.location_dest_id.id,
            "location_dest_name": self.location_dest_id.display_name,
            "locked_source_location_id": source.id or False,
            "locked_source_location_name": source.display_name or "",
            "locked_dest_location_id": dest.id or False,
            "locked_dest_location_name": dest.display_name or "",
        }

    def _align_branch_move_lines(self, role, location):
        field_name = "location_dest_id" if role == "dest" else "location_id"
        moves = self.move_ids.filtered(
            lambda move: move.state not in ("done", "cancel") and move[field_name] != location
        )
        if moves:
            moves.with_context(skip_branch_location_check=True).write({field_name: location.id})
        lines = self.move_line_ids.filtered(
            lambda line: line.state not in ("done", "cancel") and line[field_name] != location
        )
        if lines:
            lines.with_context(skip_branch_location_check=True).write({field_name: location.id})

    def _lock_branch_location(self, role, location):
        """Lock and override the picking location from the first accepted scan."""
        self.ensure_one()
        self._check_branch_scanned_location(location)
        locked = (
            self.barcode_locked_dest_location_id
            if role == "dest"
            else self.barcode_locked_source_location_id
        )
        if locked and locked != location:
            raise UserError(self._branch_location_mismatch_message(role, locked))
        if locked:
            return self._branch_location_payload(role)
        vals = (
            {
                "barcode_locked_dest_location_id": location.id,
                "location_dest_id": location.id,
            }
            if role == "dest"
            else {
                "barcode_locked_source_location_id": location.id,
                "location_id": location.id,
            }
        )
        self.with_context(skip_branch_location_check=True).write(vals)
        self._align_branch_move_lines(role, location)
        return self._branch_location_payload(role)

    def apply_branch_barcode_location(self, location_id, role):
        """Replace the transfer location on the first scan and reject a different one."""
        self.ensure_one()
        if not self._branch_location_override_enabled():
            return {"applied": False}

        location = self.env["stock.location"].browse(location_id).exists()
        if not self.barcode_locked_source_location_id:
            role = "source"
        elif role not in ("source", "dest"):
            role = "source"
        if role == "dest" and self.picking_type_id.restrict_scan_dest_location == "no":
            role = "source"
        return self._lock_branch_location(role, location)

    def _apply_branch_location_from_line(self, role, location):
        """Fallback when barcode wrote a line location before JS could lock the picking."""
        self.ensure_one()
        if not location or not self._branch_location_override_enabled():
            return
        locked = (
            self.barcode_locked_dest_location_id
            if role == "dest"
            else self.barcode_locked_source_location_id
        )
        if locked:
            if location != locked:
                raise UserError(self._branch_location_mismatch_message(role, locked))
            return
        # First concrete line location becomes the locked override for that role.
        self._lock_branch_location(role, location)
