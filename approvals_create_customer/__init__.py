# -*- coding: utf-8 -*-
from . import models
from . import controllers


def post_init_hook(env):
    """Keep Create Customer free of approval_contact VAT/attachment rules."""
    category = env.ref(
        "approvals_create_customer.approval_category_data_create_customer",
        raise_if_not_found=False,
    )
    if category and "x_create_contact_on_approve" in category._fields and category.x_create_contact_on_approve:
        category.x_create_contact_on_approve = False
