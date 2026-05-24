from odoo import api, fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    # Department categories
    is_export_customer = fields.Boolean(
        string='Export Sales Customer',
        default=False,
        help='Customer belongs to Export Sales department'
    )
    is_local_customer = fields.Boolean(
        string='Local Sales Customer',
        default=False,
        help='Customer belongs to Local Sales department'
    )
    is_vendor = fields.Boolean(
        string='Vendor (Procurement)',
        default=False,
        help='Partner is a vendor for Procurement department'
    )
    is_pos_customer = fields.Boolean(
        string='POS Customer',
        default=False,
        help='Customer created from Point of Sale'
    )

    department_category = fields.Selection(
        selection=[
            ('export', 'Export Sales'),
            ('local', 'Local Sales'),
            ('procurement', 'Procurement/Vendor'),
            ('pos', 'POS'),
        ],
        string='Department Category',
        compute='_compute_department_category',
        store=True,
        help='Automatically computed based on department flags'
    )

    @api.depends('is_vendor', 'is_export_customer', 'is_local_customer', 'is_pos_customer')
    def _compute_department_category(self):
        """Compute the primary department category based on flags."""
        for partner in self:
            if partner.is_vendor:
                partner.department_category = 'procurement'
            elif partner.is_export_customer:
                partner.department_category = 'export'
            elif partner.is_local_customer:
                partner.department_category = 'local'
            elif partner.is_pos_customer:
                partner.department_category = 'pos'
            else:
                partner.department_category = False

    @api.model
    def _load_pos_data_fields(self, config):
        """
        Ensure POS receives is_pos_customer so frontend filtering
        can hide non-POS customers without access-rule side effects.
        """
        fields_list = super()._load_pos_data_fields(config)
        if 'is_pos_customer' not in fields_list:
            fields_list.append('is_pos_customer')
        return fields_list
