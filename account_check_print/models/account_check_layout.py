from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class AccountCheckLayout(models.Model):
    """Store the physical dimensions and field positions of a check stock."""

    _name = "account.check.layout"
    _description = "Check Layout"
    _order = "company_id, name"
    _check_company_auto = True

    name = fields.Char(required=True, translate=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
        index=True,
        ondelete="cascade",
    )
    paper_width = fields.Float(
        string="Paper Width (mm)", required=True, default=216.0
    )
    paper_height = fields.Float(
        string="Paper Height (mm)", required=True, default=92.0
    )
    dpi = fields.Integer(required=True, default=96)
    font_size = fields.Float(string="Default Font Size (pt)", default=11.0)
    background_image = fields.Binary(attachment=True)
    background_filename = fields.Char()
    logo_image = fields.Binary(attachment=True)
    signature_image = fields.Binary(attachment=True)
    paperformat_id = fields.Many2one(
        "report.paperformat", copy=False, readonly=True, ondelete="set null"
    )

    date_x = fields.Float(default=165.0)
    date_y = fields.Float(default=12.0)
    date_width = fields.Float(default=38.0)
    date_height = fields.Float(default=8.0)
    payee_x = fields.Float(default=25.0)
    payee_y = fields.Float(default=28.0)
    payee_width = fields.Float(default=130.0)
    payee_height = fields.Float(default=9.0)
    amount_x = fields.Float(default=165.0)
    amount_y = fields.Float(default=28.0)
    amount_width = fields.Float(default=38.0)
    amount_height = fields.Float(default=9.0)
    amount_words_x = fields.Float(default=25.0)
    amount_words_y = fields.Float(default=41.0)
    amount_words_width = fields.Float(default=178.0)
    amount_words_height = fields.Float(default=12.0)
    memo_x = fields.Float(default=25.0)
    memo_y = fields.Float(default=62.0)
    memo_width = fields.Float(default=95.0)
    memo_height = fields.Float(default=9.0)
    signature_x = fields.Float(default=145.0)
    signature_y = fields.Float(default=59.0)
    signature_width = fields.Float(default=58.0)
    signature_height = fields.Float(default=20.0)
    logo_x = fields.Float(default=8.0)
    logo_y = fields.Float(default=6.0)
    logo_width = fields.Float(default=30.0)
    logo_height = fields.Float(default=18.0)
    check_number_x = fields.Float(default=170.0)
    check_number_y = fields.Float(default=4.0)
    check_number_width = fields.Float(default=33.0)
    check_number_height = fields.Float(default=7.0)

    _name_company_unique = models.Constraint(
        "UNIQUE(name, company_id)",
        "A check layout name must be unique per company.",
    )

    @api.constrains("paper_width", "paper_height", "dpi", "font_size")
    def _check_positive_dimensions(self):
        """Reject dimensions that cannot produce a valid PDF."""
        for layout in self:
            if layout.paper_width <= 0 or layout.paper_height <= 0:
                raise ValidationError(_("Paper dimensions must be greater than zero."))
            if not 72 <= layout.dpi <= 600:
                raise ValidationError(_("DPI must be between 72 and 600."))
            if layout.font_size <= 0:
                raise ValidationError(_("Font size must be greater than zero."))

    @api.constrains(
        "paper_width", "paper_height",
        "date_x", "date_y", "date_width", "date_height",
        "payee_x", "payee_y", "payee_width", "payee_height",
        "amount_x", "amount_y", "amount_width", "amount_height",
        "amount_words_x", "amount_words_y", "amount_words_width",
        "amount_words_height", "memo_x", "memo_y", "memo_width",
        "memo_height", "signature_x", "signature_y", "signature_width",
        "signature_height", "logo_x", "logo_y", "logo_width", "logo_height",
        "check_number_x", "check_number_y", "check_number_width",
        "check_number_height",
    )
    def _check_field_geometry(self):
        """Keep every configured field inside the physical page."""
        for layout in self:
            for field_name in self._designer_field_names():
                x = layout[f"{field_name}_x"]
                y = layout[f"{field_name}_y"]
                width = layout[f"{field_name}_width"]
                height = layout[f"{field_name}_height"]
                if min(x, y) < 0 or width <= 0 or height <= 0:
                    raise ValidationError(
                        _("%s has invalid coordinates or dimensions.", field_name)
                    )
                if x + width > layout.paper_width or y + height > layout.paper_height:
                    raise ValidationError(_("%s extends beyond the paper.", field_name))

    @api.model
    def _designer_field_names(self):
        """Return the stable field keys shared by the designer and report."""
        return (
            "date", "payee", "amount", "amount_words", "memo",
            "signature", "logo", "check_number",
        )

    @api.model_create_multi
    def create(self, vals_list):
        """Create a matching custom paper format for each layout."""
        layouts = super().create(vals_list)
        for layout in layouts:
            layout.paperformat_id = layout._create_paperformat().id
        return layouts

    def write(self, vals):
        """Synchronize layout page settings with wkhtmltopdf configuration."""
        result = super().write(vals)
        if {"name", "paper_width", "paper_height", "dpi"} & set(vals):
            for layout in self:
                layout._sync_paperformat()
        return result

    def unlink(self):
        """Remove private paper formats after their layouts are deleted."""
        paperformats = self.mapped("paperformat_id")
        result = super().unlink()
        paperformats.sudo().unlink()
        return result

    def _paperformat_values(self):
        """Build a borderless custom paper format for this layout."""
        self.ensure_one()
        return {
            "name": _("Check: %s", self.name),
            "format": "custom",
            "page_width": self.paper_width,
            "page_height": self.paper_height,
            "orientation": "Portrait",
            "margin_top": 0,
            "margin_bottom": 0,
            "margin_left": 0,
            "margin_right": 0,
            "header_line": False,
            "header_spacing": 0,
            "dpi": self.dpi,
        }

    def _create_paperformat(self):
        """Create the report.paperformat owned by this layout."""
        self.ensure_one()
        return self.env["report.paperformat"].sudo().create(self._paperformat_values())

    def _sync_paperformat(self):
        """Create or update the paper format without sharing mutable records."""
        self.ensure_one()
        if self.paperformat_id:
            self.paperformat_id.sudo().write(self._paperformat_values())
        else:
            self.paperformat_id = self._create_paperformat().id

    def action_open_designer(self):
        """Open the OWL visual designer for this layout."""
        self.ensure_one()
        self.check_access("write")
        return {
            "type": "ir.actions.client",
            "tag": "account_check_print.layout_designer",
            "name": _("Check Layout Designer"),
            "params": {"layout_id": self.id},
        }

    def get_designer_data(self):
        """Return serializable geometry and sample text to the OWL client."""
        self.ensure_one()
        self.check_access("read")
        geometry = {
            name: {
                key: self[f"{name}_{key}"]
                for key in ("x", "y", "width", "height")
            }
            for name in self._designer_field_names()
        }
        return {
            "id": self.id,
            "name": self.name,
            "paper_width": self.paper_width,
            "paper_height": self.paper_height,
            "font_size": self.font_size,
            "background_url": (
                f"/web/image/account.check.layout/{self.id}/background_image"
                if self.background_image else False
            ),
            "fields": geometry,
        }

    def save_designer_data(self, geometry):
        """Validate and persist geometry sent by the visual designer."""
        self.ensure_one()
        self.check_access("write")
        values = {}
        for name in self._designer_field_names():
            item = geometry.get(name, {})
            for key in ("x", "y", "width", "height"):
                if key not in item:
                    raise ValidationError(_("Incomplete geometry for %s.", name))
                values[f"{name}_{key}"] = float(item[key])
        self.write(values)
        return True
