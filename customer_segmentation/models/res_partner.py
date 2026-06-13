import logging

from odoo import api, fields, models
from odoo.osv import expression


_logger = logging.getLogger(__name__)


class ResPartner(models.Model):
    _inherit = 'res.partner'

    def _get_group_segmentation_domain(self, user):
        """Build partner filter domain based on customer segmentation groups."""
        group_domains = []
        if user.has_group('customer_segmentation.group_export_sales'):
            group_domains.append([('is_export_customer', '=', True)])
        if user.has_group('customer_segmentation.group_local_sales'):
            group_domains.append([('is_local_customer', '=', True)])
        if user.has_group('customer_segmentation.group_procurement'):
            group_domains.append([('is_vendor', '=', True)])
        if user.has_group('customer_segmentation.group_pos_team'):
            group_domains.append([('is_pos_customer', '=', True)])
        if not group_domains:
            return []
        if len(group_domains) == 1:
            return group_domains[0]
        return expression.OR(group_domains)

    def _apply_segmentation_domain(self, domain):
        """
        Merge caller domain with department segmentation domain when needed.
        This ensures all search paths (name_search + Search More popup) behave
        consistently for segmented users.
        """
        base_domain = domain or []
        if self.env.context.get('skip_customer_segmentation_domain'):
            return base_domain
        segmentation_domain = self._get_group_segmentation_domain(self.env.user)
        if not segmentation_domain:
            return base_domain
        return expression.AND([base_domain, segmentation_domain])

    def _register_hook(self):
        """
        Safety net for databases that still contain the legacy
        'Admin - See All Customers' rule created in old versions.
        """
        result = super()._register_hook()
        rule = self.env.ref('customer_segmentation.rule_admin_all_customers', raise_if_not_found=False)
        if rule and rule.active:
            rule.sudo().write({'active': False})
            _logger.info(
                "[customer_segmentation] Disabled legacy rule: customer_segmentation.rule_admin_all_customers"
            )

        # Also disable any manually created global "allow all contacts" rules
        # that bypass segmentation (no group + domain [(1, '=', 1)]).
        global_open_rules = self.env['ir.rule'].sudo().search([
            ('model_id', '=', self.env['ir.model']._get_id('res.partner')),
            ('active', '=', True),
            ('domain_force', 'in', ["[(1, '=', 1)]", '[(1,"=",1)]']),
            ('groups', '=', False),
        ])
        if global_open_rules:
            global_open_rules.write({'active': False})
            _logger.info(
                "[customer_segmentation] Disabled %s global open res.partner rule(s): %s",
                len(global_open_rules),
                global_open_rules.mapped('name'),
            )
        return result

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

    def name_search(self, name='', domain=None, operator='ilike', limit=100):
        """
        Temporary diagnostic logs to understand why partner filtering
        is not applied during partner lookup (e.g. in sale order).
        """
        base_domain = domain or []
        user = self.env.user
        segmentation_domain = self._get_group_segmentation_domain(user)
        search_domain = self._apply_segmentation_domain(base_domain)
        result = super().name_search(name, search_domain, operator, limit)
        result_ids = [res_id for res_id, _label in result]

        _logger.info(
            "[customer_segmentation] name_search user=%s(id=%s) name=%s operator=%s limit=%s domain=%s seg_domain=%s final_domain=%s result_count=%s sample_ids=%s "
            "groups={export:%s, local:%s, procurement:%s, pos:%s, admin:%s}",
            user.login,
            user.id,
            name,
            operator,
            limit,
            base_domain,
            segmentation_domain,
            search_domain,
            len(result_ids),
            result_ids[:20],
            user.has_group('customer_segmentation.group_export_sales'),
            user.has_group('customer_segmentation.group_local_sales'),
            user.has_group('customer_segmentation.group_procurement'),
            user.has_group('customer_segmentation.group_pos_team'),
            user.has_group('base.group_system'),
        )
        return result

    @api.model
    def _search(self, domain, offset=0, limit=None, order=None, access_rights_uid=None):
        """
        Apply department segmentation to generic searches as well.
        Search More in many2one fields uses _search instead of name_search.
        """
        final_domain = self._apply_segmentation_domain(domain)
        return super()._search(
            final_domain,
            offset=offset,
            limit=limit,
            order=order,
            access_rights_uid=access_rights_uid,
        )

    @api.model_create_multi
    def create(self, vals_list):
        """
        Auto-tag partners by creation channel:
        - POS creation -> is_pos_customer
        - Vendors menu / supplier context -> is_vendor
        - Customer creation -> export/local/pos based on user group
        Explicit values in vals still take priority.
        """
        user = self.env.user
        ctx = self.env.context
        department_flags = (
            'is_export_customer',
            'is_local_customer',
            'is_vendor',
            'is_pos_customer',
        )

        for vals in vals_list:
            has_explicit_department = any(flag in vals for flag in department_flags)

            if not has_explicit_department and ctx.get('default_is_pos_customer'):
                vals['is_pos_customer'] = True
                has_explicit_department = True

            supplier_rank = vals.get('supplier_rank', 0) or 0
            if not has_explicit_department and (ctx.get('default_supplier_rank') or supplier_rank > 0):
                vals['is_vendor'] = True
                has_explicit_department = True

            customer_rank = vals.get('customer_rank', 0) or 0
            is_customer_context = bool(ctx.get('default_customer_rank') or customer_rank > 0)
            if not has_explicit_department and is_customer_context:
                if user.has_group('customer_segmentation.group_export_sales'):
                    vals['is_export_customer'] = True
                    has_explicit_department = True
                elif user.has_group('customer_segmentation.group_local_sales'):
                    vals['is_local_customer'] = True
                    has_explicit_department = True
                elif user.has_group('customer_segmentation.group_pos_team'):
                    vals['is_pos_customer'] = True
                    has_explicit_department = True

            if not has_explicit_department and user.has_group('customer_segmentation.group_procurement'):
                vals['is_vendor'] = True

        return super().create(vals_list)
