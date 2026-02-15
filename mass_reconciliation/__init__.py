from . import models

def post_init_hook(cr, registry):
    from .models.view_patch import post_init_hook as _hook
    _hook(cr, registry)
