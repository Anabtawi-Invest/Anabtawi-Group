# -*- coding: utf-8 -*-
from odoo import api, models


class HrJob(models.Model):
    _inherit = 'hr.job'

    @api.model
    def _search_get_detail(self, website, order, options):
        res = super()._search_get_detail(website, order, options)
        # Always enforce that only published and active jobs are listed on the website
        res['base_domain'].append([('is_published', '=', True)])
        res['base_domain'].append([('active', '=', True)])
        return res

