# -*- coding: utf-8 -*-
from odoo import fields, models

from .meps_client import DEFAULT_MEPS_TIMEOUT, DEFAULT_MEPS_URL


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    meps_endpoint_url = fields.Char(
        string="MEPS Gateway URL",
        config_parameter="pos_mep_id.endpoint_url",
        default=DEFAULT_MEPS_URL,
        help="SOAP endpoint for the MEPS/ApexECR web service. Only change this if the "
        "acquirer gave you a different (e.g. test/UAT) URL.",
    )
    meps_timeout = fields.Integer(
        string="MEPS Request Timeout (seconds)",
        config_parameter="pos_mep_id.timeout",
        default=DEFAULT_MEPS_TIMEOUT,
        help="How long to wait for the physical terminal to respond (card insert/tap, PIN, "
        "authorization) before giving up.",
    )
