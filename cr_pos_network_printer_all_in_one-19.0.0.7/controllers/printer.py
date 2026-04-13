# -*- coding: utf-8 -*-
# Part of Creyox Technologies

from odoo import http
from odoo.http import request
import logging

_logger = logging.getLogger(__name__)

# Import the base controller so we can extend it gracefully.
try:
    from odoo.addons.cr_all_in_one_direct_print.controllers.printer import CrPrinterController
except ImportError:
    CrPrinterController = http.Controller
    _logger.warning("Could not import CrPrinterController from cr_all_in_one_direct_print")

class PosPrinterController(CrPrinterController):

    @http.route()
    def print_jobs(self, **kwargs):
        """ Extend the base API endpoint to append POS specific printer details. """
        # Let the base function do validation, set jobs to 'printing', and fetch basic info
        result = super(PosPrinterController, self).print_jobs(**kwargs)

        if result and isinstance(result, list):
            job_ids = [res.get('id') for res in result if res.get('id')]
            if job_ids:
                PrintJob = request.env['print.job'].sudo()
                pos_fields = ["printer_type", "ip", "port", "is_open_cashbox"]
                
                # Check which of our POS fields actually exist in case of partial upgrades
                valid_fields = [f for f in pos_fields if f in PrintJob._fields]
                
                if valid_fields:
                    extra_data = PrintJob.browse(job_ids).read(valid_fields)
                    extra_data_map = {d['id']: d for d in extra_data}
                    
                    # Merge POS extended fields back into the base result JSON payload
                    for res in result:
                        job_id = res.get('id')
                        if job_id and job_id in extra_data_map:
                            res.update(extra_data_map[job_id])
                            
        return result
