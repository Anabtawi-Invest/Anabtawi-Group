import base64
import io

from odoo import _, api, fields, models
from odoo.exceptions import UserError

try:
    import xlsxwriter
except ImportError:
    xlsxwriter = None


class ConstructionProject(models.Model):
    _name = "construction.project"
    _description = "Construction Project (Budget Control)"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "name"

    name = fields.Char(required=True, tracking=True)
    code = fields.Char(string="Project Code", tracking=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(related="company_id.currency_id", string="Currency", readonly=True)
    partner_id = fields.Many2one("res.partner", string="Client / Owner")
    project_manager_id = fields.Many2one("res.users", string="Project Manager", tracking=True)
    site_address = fields.Text(string="Site Address")
    date_start = fields.Date(string="Start Date")
    date_end = fields.Date(string="Target End Date")
    state = fields.Selection(
        [("planning", "Planning"), ("active", "Active"), ("on_hold", "On Hold"), ("closed", "Closed")],
        default="planning",
        tracking=True,
    )
    total_budget = fields.Monetary(string="Total Approved Budget", required=True, tracking=True)

    material_ids = fields.One2many(
        "construction.project.budget.material", "project_id", string="Project Budget Materials"
    )
    material_count = fields.Integer(compute="_compute_material_stats", string="Material Count")
    materials_total_cost = fields.Monetary(
        compute="_compute_material_stats", string="Approved Materials Total Cost", store=True
    )

    po_ids = fields.One2many("construction.budget.po", "project_id", string="Purchase Orders")
    po_count = fields.Integer(compute="_compute_po_stats")
    approved_amount = fields.Monetary(compute="_compute_po_stats", store=True)
    pending_amount = fields.Monetary(compute="_compute_po_stats", store=True)
    remaining_budget = fields.Monetary(compute="_compute_po_stats", store=True)
    budget_used_pct = fields.Float(compute="_compute_po_stats", string="% Committed")

    construction_invoice_ids = fields.One2many("construction.budget.invoice", "project_id", string="Vendor Invoices")
    construction_invoice_count = fields.Integer(compute="_compute_project_counts", string="Invoice Count")

    receipt_ids = fields.One2many("construction.budget.receipt", "project_id", string="Item Receipts")
    receipt_count = fields.Integer(compute="_compute_project_counts", string="Receipt Count")

    @api.depends("material_ids", "material_ids.state", "material_ids.total_cost")
    def _compute_material_stats(self):
        for project in self:
            project.material_count = len(project.material_ids)
            project.materials_total_cost = sum(
                project.material_ids.filtered(lambda m: m.state == "approved").mapped("total_cost")
            )

    @api.depends("po_ids", "construction_invoice_ids", "receipt_ids")
    def _compute_project_counts(self):
        for project in self:
            project.construction_invoice_count = len(project.construction_invoice_ids)
            project.receipt_count = len(project.receipt_ids)

    def action_submit_draft_materials(self):
        self.ensure_one()
        draft_materials = self.material_ids.filtered(lambda m: m.state == "draft")
        if not draft_materials:
            raise UserError(_("There are no draft budget materials to submit."))
        draft_materials.action_submit()
        return True

    def action_accounting_approve_materials(self):
        self.ensure_one()
        materials = self.material_ids.filtered(lambda m: m.state == "accounting_review")
        if not materials:
            raise UserError(_("There are no materials waiting for Accounting approval."))
        materials.action_accounting_approve()
        return True

    def action_ceo_approve_materials(self):
        self.ensure_one()
        materials = self.material_ids.filtered(lambda m: m.state == "ceo_review")
        if not materials:
            raise UserError(_("There are no materials waiting for CEO approval."))
        materials.action_ceo_approve()
        return True

    def action_chairman_approve_materials(self):
        self.ensure_one()
        materials = self.material_ids.filtered(lambda m: m.state == "chairman_review")
        if not materials:
            raise UserError(_("There are no materials waiting for Chairman approval."))
        materials.action_chairman_approve()
        return True


    @api.depends("total_budget", "po_ids.amount", "po_ids.state")
    def _compute_po_stats(self):
        pending_states = ("accounting_review", "gm_review", "chairman_review")
        for project in self:
            pos = project.po_ids
            approved = sum(pos.filtered(lambda p: p.state == "approved").mapped("amount"))
            pending = sum(pos.filtered(lambda p: p.state in pending_states).mapped("amount"))
            project.po_count = len(pos)
            project.approved_amount = approved
            project.pending_amount = pending
            project.remaining_budget = project.total_budget - approved - pending
            project.budget_used_pct = (
                (approved + pending) / project.total_budget * 100 if project.total_budget else 0.0
            )

    def action_view_pos(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Purchase Orders"),
            "res_model": "construction.budget.po",
            "view_mode": "list,form",
            "domain": [("project_id", "=", self.id)],
            "context": {"default_project_id": self.id},
        }

    def action_view_invoices(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Vendor Bills"),
            "res_model": "construction.budget.invoice",
            "view_mode": "list,form",
            "domain": [("project_id", "=", self.id)],
            "context": {"default_project_id": self.id},
        }

    def action_view_receipts(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Item Receipts"),
            "res_model": "construction.budget.receipt",
            "view_mode": "list,form",
            "domain": [("project_id", "=", self.id)],
            "context": {"default_project_id": self.id},
        }

    def action_export_all_bom_excel(self):
        self.ensure_one()
        if not xlsxwriter:
            raise UserError(_(
                "The 'xlsxwriter' Python library is required for Excel export. "
                "Please ask your administrator to install it (pip install xlsxwriter)."
            ))
        if not self.po_ids:
            raise UserError(_("This project has no Purchase Orders to export."))

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {"in_memory": True})
        bold = workbook.add_format({"bold": True, "font_size": 14})
        header_fmt = workbook.add_format({"bold": True, "bg_color": "#D9D9D9", "border": 1})
        cell_fmt = workbook.add_format({"border": 1})
        money_fmt = workbook.add_format({"border": 1, "num_format": "#,##0.00"})
        total_fmt = workbook.add_format({"bold": True, "border": 1, "num_format": "#,##0.00"})

        summary = workbook.add_worksheet("Summary")
        summary.write(0, 0, "Project BOM Export - %s" % self.name, bold)
        headers = ["PO Reference", "Vendor", "Status", "PO Amount", "BOM Lines Total"]
        for col, h in enumerate(headers):
            summary.write(2, col, h, header_fmt)
        row = 3
        used_names = set()
        for po in self.po_ids:
            summary.write(row, 0, po.name, cell_fmt)
            summary.write(row, 1, po.vendor_id.name or "", cell_fmt)
            summary.write(row, 2, dict(po._fields["state"].selection).get(po.state), cell_fmt)
            summary.write(row, 3, po.amount, money_fmt)
            summary.write(row, 4, po.lines_total, money_fmt)
            row += 1

            base_name = (po.name or "PO%s" % po.id).replace("/", "-")[:28]
            sheet_name = base_name
            i = 1
            while sheet_name in used_names:
                sheet_name = ("%s_%s" % (base_name, i))[:31]
                i += 1
            used_names.add(sheet_name)

            po_sheet = workbook.add_worksheet(sheet_name)
            po_sheet.write(0, 0, "%s - %s" % (po.name, po.vendor_id.name or ""), bold)
            po._write_bom_lines(po_sheet, header_fmt, cell_fmt, money_fmt, total_fmt, start_row=2)

        summary.set_column(0, 0, 20)
        summary.set_column(1, 1, 30)
        summary.set_column(2, 2, 18)
        summary.set_column(3, 4, 16)

        workbook.close()
        output.seek(0)
        attachment = self.env["ir.attachment"].create({
            "name": "BOM_Export_%s.xlsx" % self.name,
            "datas": base64.b64encode(output.read()),
            "res_model": self._name,
            "res_id": self.id,
            "mimetype": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        })
        return {
            "type": "ir.actions.act_url",
            "url": "/web/content/%s?download=true" % attachment.id,
            "target": "self",
        }
