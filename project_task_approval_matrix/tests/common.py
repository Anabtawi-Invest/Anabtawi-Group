from odoo import Command
from odoo.tests.common import TransactionCase


class ApprovalMatrixCase(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.group_manager = cls.env.ref(
            "project_task_approval_matrix.group_project_approval_manager"
        )
        cls.group_approver = cls.env.ref(
            "project_task_approval_matrix.group_project_task_approver"
        )
        cls.group_project_user = cls.env.ref("project.group_project_user")
        cls.env.user.group_ids = [Command.link(cls.group_manager.id)]
        cls.manager = cls.env.user

        cls.approver_1 = cls._create_user("approval_one", cls.group_approver)
        cls.approver_2 = cls._create_user("approval_two", cls.group_approver)
        cls.approver_3 = cls._create_user("approval_three", cls.group_approver)
        cls.task_user = cls._create_user("approval_task_user", cls.group_project_user)

        cls.project = cls.env["project.project"].create(
            {
                "name": "Approval Test Project",
                "approval_matrix_enabled": True,
                "prevent_task_completion_without_approval": True,
                "prevent_self_approval": True,
            }
        )
        cls.open_stage = cls.env["project.task.type"].create(
            {
                "name": "Approval Open",
                "project_ids": [Command.link(cls.project.id)],
            }
        )
        cls.closing_stage = cls.env["project.task.type"].create(
            {
                "name": "Approval Closed",
                "approval_closing_stage": True,
                "project_ids": [Command.link(cls.project.id)],
            }
        )
        cls.project.type_ids = [
            Command.link(cls.open_stage.id),
            Command.link(cls.closing_stage.id),
        ]

    @classmethod
    def _create_user(cls, login, group):
        return cls.env["res.users"].with_context(no_reset_password=True).create(
            {
                "name": login.replace("_", " ").title(),
                "login": login,
                "email": f"{login}@example.com",
                "company_id": cls.company.id,
                "company_ids": [Command.set([cls.company.id])],
                "group_ids": [Command.set([group.id])],
            }
        )

    def _new_task(self, approval_type="sequential", **extra_values):
        values = {
            "name": "Controlled Task",
            "project_id": self.project.id,
            "stage_id": self.open_stage.id,
            "user_ids": [Command.set([self.task_user.id])],
            "approval_required": True,
            "approval_type": approval_type,
        }
        values.update(extra_values)
        return self.env["project.task"].create(values)

    def _add_route(self, task, users=None):
        users = users or [self.approver_1, self.approver_2]
        return self.env["project.task.approval.line"].create(
            [
                {
                    "task_id": task.id,
                    "sequence": index * 10,
                    "approver_id": user.id,
                    "approver_role": f"Step {index}",
                }
                for index, user in enumerate(users, start=1)
            ]
        )

    def _linked_activities(self, task):
        return self.env["mail.activity"].search(
            [
                ("res_model", "=", "project.task"),
                ("res_id", "=", task.id),
                ("project_task_approval_line_id", "!=", False),
            ]
        )
