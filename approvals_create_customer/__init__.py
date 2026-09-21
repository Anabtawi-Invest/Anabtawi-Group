# -*- coding: utf-8 -*-
from . import models
from . import controllers


def post_init_hook(env):
    """Ensure the Create Customer category uses approval_contact creation fields."""
    category = env.ref(
        "approvals_create_customer.approval_category_data_create_customer",
        raise_if_not_found=False,
    )
    if category and not category.x_create_contact_on_approve:
        category.x_create_contact_on_approve = True
