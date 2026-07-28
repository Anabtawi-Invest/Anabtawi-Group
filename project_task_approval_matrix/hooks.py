def post_init_hook(env):
    """Initialize allocation display fields without changing allocated hours."""
    tasks = env["project.task"].with_context(active_test=False).search([])
    for task in tasks:
        task.write(
            {
                "allocation_unit": "hours",
                "allocation_value": task.allocated_hours,
            }
        )
