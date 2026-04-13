# -*- coding: utf-8 -*-
# Part of Creyox Technologies

from . import printer

from werkzeug.serving import WSGIRequestHandler

# Save original method
_original_log = WSGIRequestHandler.log


def custom_log(self, type, message, *args):
    """To skip the logs of /api/print_job"""
    if args and "/api/print_job" in args[0]:
        return
    return _original_log(self, type, message, *args)

WSGIRequestHandler.log = custom_log
