# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class PrintJob(models.Model):
    _inherit = 'print.job'

    pos_config_id = fields.Many2one('pos.config', string='POS Configuration', help="POS Config that dispatched this print job")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            pos_config_id = vals.get('pos_config_id')
            
            # If pos_config_id wasn't passed explicitly in JS RPC, try fetching active session
            if not pos_config_id:
                active_session = self.env['pos.session'].search([
                    ('user_id', '=', self.env.uid),
                    ('state', '=', 'opened')
                ], limit=1)
                if active_session:
                    pos_config_id = active_session.config_id.id
                    vals['pos_config_id'] = pos_config_id

            if pos_config_id:
                pos_config = self.env['pos.config'].browse(pos_config_id)
                assigned_branch_printer = pos_config.branch_printer_id

                if assigned_branch_printer:
                    target_ip = vals.get('ip')
                    target_printer_id = vals.get('printer_id')

                    # 1. Check IP address mismatch if LAN printer
                    if assigned_branch_printer.connection_type == 'lan' and target_ip:
                        if assigned_branch_printer.ip_address and target_ip != assigned_branch_printer.ip_address:
                            raise UserError(_(
                                "Security Warning: POS Config '%(pos)s' (Branch %(branch)s) is restricted to printer IP %(assigned_ip)s. "
                                "Attempted to print to unauthorized printer at IP %(target_ip)s!"
                            ) % {
                                'pos': pos_config.name,
                                'branch': assigned_branch_printer.branch_code,
                                'assigned_ip': assigned_branch_printer.ip_address,
                                'target_ip': target_ip,
                            })

                    # 2. Check Printer Record mismatch
                    if assigned_branch_printer.printer_id and target_printer_id:
                        if target_printer_id != assigned_branch_printer.printer_id.id:
                            raise UserError(_(
                                "Security Warning: Branch '%(branch)s' is not allowed to send print jobs to another branch's printer!"
                            ) % {
                                'branch': assigned_branch_printer.branch_code,
                            })

        return super().create(vals_list)
