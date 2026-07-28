from odoo import Command
from odoo.exceptions import AccessError, ValidationError

from .common import ApprovalMatrixCase


class TestApprovalSecurity(ApprovalMatrixCase):
    def test_only_assigned_pending_approver_can_decide(self):
        task = self._new_task()
        lines = self._add_route(task)
        task.action_submit_for_approval()
        with self.assertRaises(AccessError):
            task.with_user(self.approver_2).action_approve()
        with self.assertRaises(AccessError):
            lines[0].with_user(self.approver_2).write(
                {"comments": "Forged comment"}
            )
        with self.assertRaises(AccessError):
            task.with_user(self.approver_1).write({"approval_state": "approved"})

    def test_manager_reset_and_controlled_override(self):
        task = self._new_task()
        self._add_route(task)
        task.action_submit_for_approval()
        with self.assertRaises(AccessError):
            task.with_user(self.approver_1).action_reset_approval()
        task.action_reset_approval()
        self.assertEqual(task.approval_state, "draft")
        self.assertFalse(self._linked_activities(task))

        task.approval_manager_override_reason = "Executive exception."
        task.action_manager_override_approve()
        self.assertEqual(task.approval_state, "approved")
        self.assertEqual(set(task.approval_line_ids.mapped("state")), {"approved"})

    def test_self_approval_is_blocked_but_manager_override_is_audited(self):
        task = self._new_task(user_ids=[Command.set([self.approver_1.id])])
        self._add_route(task, [self.approver_1])
        with self.assertRaises(ValidationError):
            task.action_submit_for_approval()
        task.approval_manager_override_reason = "Documented urgent exception."
        task.action_manager_override_approve()
        self.assertEqual(task.approval_state, "approved")

    def test_portal_has_no_approval_line_access(self):
        task = self._new_task()
        line = self._add_route(task, [self.approver_1])
        portal = self.env["res.users"].with_context(no_reset_password=True).create(
            {
                "name": "Approval Portal",
                "login": "approval_portal",
                "group_ids": [Command.set([self.env.ref("base.group_portal").id])],
            }
        )
        with self.assertRaises(AccessError):
            line.with_user(portal).check_access("read")

    def test_multi_company_rule(self):
        other_company = self.env["res.company"].create({"name": "Other Approval Co"})
        self.manager.company_ids = [Command.link(other_company.id)]
        other_project = self.env["project.project"].with_company(other_company).create(
            {
                "name": "Other Company Project",
                "company_id": other_company.id,
                "approval_matrix_enabled": True,
            }
        )
        other_task = self.env["project.task"].with_company(other_company).create(
            {
                "name": "Other Company Task",
                "project_id": other_project.id,
                "approval_required": True,
            }
        )
        other_user = self.env["res.users"].create(
            {
                "name": "Other Approver",
                "login": "other_approver",
                "company_id": other_company.id,
                "company_ids": [Command.set([other_company.id])],
                "group_ids": [Command.set([self.group_approver.id])],
            }
        )
        line = self.env["project.task.approval.line"].with_company(
            other_company
        ).create(
            {
                "task_id": other_task.id,
                "approver_id": other_user.id,
            }
        )
        with self.assertRaises(AccessError):
            line.with_user(self.approver_1).check_access("read")
