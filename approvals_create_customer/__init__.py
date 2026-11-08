# -*- coding: utf-8 -*-
from . import models
from . import controllers


def post_init_hook(env):
    """Create one Create Customer approval category for every company."""
    env["approval.category"]._ensure_create_customer_categories()
