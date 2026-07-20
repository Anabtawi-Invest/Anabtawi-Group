<?xml version="1.0" encoding="utf-8"?>
<odoo>

    <!-- ============================================================ -->
    <!-- Sanitation program (SSOP)                                    -->
    <!-- ============================================================ -->
    <record id="view_qc_sanitation_task_list" model="ir.ui.view">
        <field name="name">qc.sanitation.task.list</field>
        <field name="model">qc.sanitation.task</field>
        <field name="arch" type="xml">
            <list string="Sanitation Tasks">
                <field name="name"/>
                <field name="branch_id"/>
                <field name="area" optional="show"/>
                <field name="frequency"/>
                <field name="requires_verification" optional="show"/>
                <field name="company_id" groups="base.group_multi_company" optional="hide"/>
            </list>
        </field>
    </record>

    <record id="view_qc_sanitation_task_form" model="ir.ui.view">
        <field name="name">qc.sanitation.task.form</field>
        <field name="model">qc.sanitation.task</field>
        <field name="arch" type="xml">
            <form string="Sanitation Task">
                <sheet>
                    <widget name="web_ribbon" title="Archived" bg_color="text-bg-danger"
                            invisible="active"/>
                    <div class="oe_title">
                        <label for="name"/>
                        <h1><field name="name" placeholder="e.g. Deep-clean walk-in fridge"/></h1>
                    </div>
                    <group>
                        <group>
                            <field name="branch_id"/>
                            <field name="area"/>
                            <field name="frequency"/>
                        </group>
                        <group>
                            <field name="requires_verification"/>
                            <field name="company_id" groups="base.group_multi_company"/>
                            <field name="active" invisible="1"/>
                        </group>
                    </group>
                    <group string="Method">
                        <field name="method" nolabel="1"/>
                    </group>
                    <field name="note" placeholder="Notes..."/>
                </sheet>
            </form>
        </field>
    </record>

    <record id="action_qc_sanitation_task" model="ir.actions.act_window">
        <field name="name">Sanitation Tasks</field>
        <field name="res_model">qc.sanitation.task</field>
        <field name="view_mode">list,form</field>
        <field name="help" type="html">
            <p class="o_view_nocontent_smiling_face">Define a sanitation task</p>
            <p>Recurring cleaning/sanitation tasks per site. A log is generated
               automatically for each due date (GMP SSOP).</p>
        </field>
    </record>

    <record id="view_qc_sanitation_log_list" model="ir.ui.view">
        <field name="name">qc.sanitation.log.list</field>
        <field name="model">qc.sanitation.log</field>
        <field name="arch" type="xml">
            <list string="Sanitation Logs"
                  decoration-danger="verification_result == 'fail'"
                  decoration-success="state == 'verified' and verification_result == 'pass'">
                <field name="name"/>
                <field name="task_id"/>
                <field name="branch_id"/>
                <field name="date"/>
                <field name="done_by_id" optional="show"/>
                <field name="state" widget="badge"
                       decoration-success="state == 'verified'"
                       decoration-warning="state == 'done'"/>
                <field name="verification_result" optional="show"/>
                <field name="company_id" groups="base.group_multi_company" optional="hide"/>
            </list>
        </field>
    </record>

    <record id="view_qc_sanitation_log_form" model="ir.ui.view">
        <field name="name">qc.sanitation.log.form</field>
        <field name="model">qc.sanitation.log</field>
        <field name="arch" type="xml">
            <form string="Sanitation Log">
                <header>
                    <button name="action_done" string="Mark Done" type="object"
                            class="oe_highlight" invisible="state != 'todo'"/>
                    <button name="action_verify" string="Verify" type="object"
                            class="oe_highlight" invisible="state != 'done'"
                            groups="site_quality_control.group_qc_branch_manager"/>
                    <field name="state" widget="statusbar"
                           statusbar_visible="todo,done,verified"/>
                </header>
                <sheet>
                    <div class="oe_title">
                        <label for="name"/>
                        <h1><field name="name" readonly="1"/></h1>
                    </div>
                    <group>
                        <group>
                            <field name="task_id" readonly="state != 'todo'"/>
                            <field name="branch_id" readonly="state != 'todo'"/>
                            <field name="date" readonly="state != 'todo'"/>
                            <field name="done_by_id"/>
                            <field name="company_id" groups="base.group_multi_company"/>
                        </group>
                        <group>
                            <field name="verification_result"
                                   invisible="state == 'todo'"/>
                            <field name="verified_by_id"/>
                            <field name="verification_date"/>
                            <field name="corrective_action_id" readonly="1"/>
                        </group>
                    </group>
                    <group string="Evidence">
                        <field name="photo_before" widget="image"/>
                        <field name="photo_after" widget="image"/>
                    </group>
                    <field name="note" placeholder="Notes..."/>
                </sheet>
                <chatter/>
            </form>
        </field>
    </record>

    <record id="view_qc_sanitation_log_search" model="ir.ui.view">
        <field name="name">qc.sanitation.log.search</field>
        <field name="model">qc.sanitation.log</field>
        <field name="arch" type="xml">
            <search string="Sanitation Logs">
                <field name="name"/>
                <field name="task_id"/>
                <field name="branch_id"/>
                <filter name="todo" string="To Do" domain="[('state', '=', 'todo')]"/>
                <filter name="failed" string="Failed Verification"
                        domain="[('verification_result', '=', 'fail')]"/>
                <group>
                    <filter name="group_branch" string="Site"
                            context="{'group_by': 'branch_id'}"/>
                    <filter name="group_task" string="Task"
                            context="{'group_by': 'task_id'}"/>
                    <filter name="group_state" string="Status"
                            context="{'group_by': 'state'}"/>
                </group>
            </search>
        </field>
    </record>

    <record id="action_qc_sanitation_log" model="ir.actions.act_window">
        <field name="name">Sanitation Logs</field>
        <field name="res_model">qc.sanitation.log</field>
        <field name="view_mode">list,form</field>
        <field name="search_view_id" ref="view_qc_sanitation_log_search"/>
        <field name="help" type="html">
            <p class="o_view_nocontent_smiling_face">No sanitation logs yet</p>
            <p>Generated automatically per sanitation task and frequency, or
               create one manually.</p>
        </field>
    </record>

    <!-- ============================================================ -->
    <!-- Personnel health / hygiene                                   -->
    <!-- ============================================================ -->
    <record id="view_qc_personnel_health_list" model="ir.ui.view">
        <field name="name">qc.personnel.health.list</field>
        <field name="model">qc.personnel.health</field>
        <field name="arch" type="xml">
            <list string="Personnel Health Declarations"
                  decoration-danger="fitness_status == 'excluded'"
                  decoration-warning="fitness_status == 'restricted'">
                <field name="employee_id"/>
                <field name="branch_id"/>
                <field name="date"/>
                <field name="symptoms"/>
                <field name="fitness_status" widget="badge"
                       decoration-success="fitness_status == 'fit'"
                       decoration-warning="fitness_status == 'restricted'"
                       decoration-danger="fitness_status == 'excluded'"/>
                <field name="cleared_return_date" optional="show"/>
                <field name="company_id" groups="base.group_multi_company" optional="hide"/>
            </list>
        </field>
    </record>

    <record id="view_qc_personnel_health_form" model="ir.ui.view">
        <field name="name">qc.personnel.health.form</field>
        <field name="model">qc.personnel.health</field>
        <field name="arch" type="xml">
            <form string="Personnel Health Declaration">
                <sheet>
                    <widget name="web_ribbon" title="Excluded" bg_color="text-bg-danger"
                            invisible="fitness_status != 'excluded'"/>
                    <widget name="web_ribbon" title="Restricted" bg_color="text-bg-warning"
                            invisible="fitness_status != 'restricted'"/>
                    <group>
                        <group>
                            <field name="employee_id"/>
                            <field name="branch_id"/>
                            <field name="date"/>
                            <field name="reported_by_id"/>
                            <field name="company_id" groups="base.group_multi_company"/>
                        </group>
                        <group>
                            <field name="symptoms"/>
                            <field name="fitness_status" readonly="1"/>
                            <field name="cleared_return_date"/>
                        </group>
                    </group>
                    <group string="Details">
                        <field name="symptom_notes" nolabel="1"
                               placeholder="Details of reported symptoms..."/>
                    </group>
                    <group string="Action Taken">
                        <field name="action_taken" nolabel="1"
                               placeholder="e.g. reassigned to non-food duties, sent home..."/>
                    </group>
                    <field name="note" placeholder="Notes..."/>
                </sheet>
                <chatter/>
            </form>
        </field>
    </record>

    <record id="view_qc_personnel_health_search" model="ir.ui.view">
        <field name="name">qc.personnel.health.search</field>
        <field name="model">qc.personnel.health</field>
        <field name="arch" type="xml">
            <search string="Personnel Health Declarations">
                <field name="employee_id"/>
                <field name="branch_id"/>
                <filter name="flagged" string="Restricted / Excluded"
                        domain="[('fitness_status', '!=', 'fit')]"/>
                <group>
                    <filter name="group_branch" string="Site"
                            context="{'group_by': 'branch_id'}"/>
                    <filter name="group_status" string="Fitness Status"
                            context="{'group_by': 'fitness_status'}"/>
                </group>
            </search>
        </field>
    </record>

    <record id="action_qc_personnel_health" model="ir.actions.act_window">
        <field name="name">Personnel Health</field>
        <field name="res_model">qc.personnel.health</field>
        <field name="view_mode">list,form</field>
        <field name="search_view_id" ref="view_qc_personnel_health_search"/>
        <field name="help" type="html">
            <p class="o_view_nocontent_smiling_face">Log a health declaration</p>
            <p>Pre-shift / periodic fitness-to-work screening. Symptomatic
               staff are automatically flagged as restricted or excluded
               from open food handling (GMP prerequisite program).</p>
        </field>
    </record>

    <!-- ============================================================ -->
    <!-- Environmental monitoring                                     -->
    <!-- ============================================================ -->
    <record id="view_qc_environmental_monitoring_list" model="ir.ui.view">
        <field name="name">qc.environmental.monitoring.list</field>
        <field name="model">qc.environmental.monitoring</field>
        <field name="arch" type="xml">
            <list string="Environmental Monitoring"
                  decoration-danger="result == 'fail'"
                  decoration-success="result == 'pass'">
                <field name="name"/>
                <field name="branch_id"/>
                <field name="date"/>
                <field name="sample_type"/>
                <field name="location" optional="show"/>
                <field name="test_parameter" optional="show"/>
                <field name="measured_value" optional="hide"/>
                <field name="limit_value" optional="hide"/>
                <field name="result" widget="badge"
                       decoration-success="result == 'pass'"
                       decoration-danger="result == 'fail'"/>
                <field name="state" widget="badge" optional="show"/>
                <field name="company_id" groups="base.group_multi_company" optional="hide"/>
            </list>
        </field>
    </record>

    <record id="view_qc_environmental_monitoring_form" model="ir.ui.view">
        <field name="name">qc.environmental.monitoring.form</field>
        <field name="model">qc.environmental.monitoring</field>
        <field name="arch" type="xml">
            <form string="Environmental Monitoring Sample">
                <header>
                    <button name="action_set_result" string="Confirm Result"
                            type="object" class="oe_highlight"
                            invisible="state != 'draft'"/>
                    <field name="state" widget="statusbar"
                           statusbar_visible="draft,confirmed"/>
                </header>
                <sheet>
                    <widget name="web_ribbon" title="Failed" bg_color="text-bg-danger"
                            invisible="result != 'fail'"/>
                    <div class="oe_title">
                        <label for="name"/>
                        <h1><field name="name" readonly="1"/></h1>
                    </div>
                    <group>
                        <group>
                            <field name="branch_id" readonly="state != 'draft'"/>
                            <field name="date" readonly="state != 'draft'"/>
                            <field name="sample_type" readonly="state != 'draft'"/>
                            <field name="location" readonly="state != 'draft'"/>
                            <field name="ccp_id" readonly="state != 'draft'"/>
                            <field name="company_id" groups="base.group_multi_company"/>
                        </group>
                        <group>
                            <field name="test_parameter" readonly="state != 'draft'"/>
                            <field name="measured_value" readonly="state != 'draft'"/>
                            <field name="limit_value" readonly="state != 'draft'"/>
                            <field name="uom_name" readonly="state != 'draft'"/>
                            <field name="result" readonly="state != 'draft'"/>
                            <field name="corrective_action_id" readonly="1"/>
                        </group>
                    </group>
                    <group string="Lab">
                        <field name="lab_name"/>
                        <field name="certificate" filename="certificate_name"/>
                        <field name="certificate_name" invisible="1"/>
                    </group>
                    <field name="note" placeholder="Notes..."/>
                </sheet>
                <chatter/>
            </form>
        </field>
    </record>

    <record id="view_qc_environmental_monitoring_search" model="ir.ui.view">
        <field name="name">qc.environmental.monitoring.search</field>
        <field name="model">qc.environmental.monitoring</field>
        <field name="arch" type="xml">
            <search string="Environmental Monitoring">
                <field name="name"/>
                <field name="branch_id"/>
                <field name="sample_type"/>
                <filter name="failed" string="Failed" domain="[('result', '=', 'fail')]"/>
                <group>
                    <filter name="group_branch" string="Site"
                            context="{'group_by': 'branch_id'}"/>
                    <filter name="group_type" string="Sample Type"
                            context="{'group_by': 'sample_type'}"/>
                </group>
            </search>
        </field>
    </record>

    <record id="action_qc_environmental_monitoring" model="ir.actions.act_window">
        <field name="name">Environmental Monitoring</field>
        <field name="res_model">qc.environmental.monitoring</field>
        <field name="view_mode">list,form</field>
        <field name="search_view_id" ref="view_qc_environmental_monitoring_search"/>
        <field name="help" type="html">
            <p class="o_view_nocontent_smiling_face">Log a sample</p>
            <p>Swab, water, air or product samples that verify sanitation and
               process controls are effective. Failed results automatically
               raise a corrective action.</p>
        </field>
    </record>

    <!-- ============================================================ -->
    <!-- Change control                                                -->
    <!-- ============================================================ -->
    <record id="view_qc_change_control_form" model="ir.ui.view">
        <field name="name">qc.change.control.form</field>
        <field name="model">qc.change.control</field>
        <field name="arch" type="xml">
            <form string="Change Control">
                <header>
                    <button name="action_submit" string="Submit" type="object"
                            class="oe_highlight" invisible="state != 'draft'"/>
                    <button name="action_approve" string="Approve" type="object"
                            class="oe_highlight" invisible="state != 'submitted'"
                            groups="site_quality_control.group_qc_quality_manager"/>
                    <button name="action_reject" string="Reject" type="object"
                            invisible="state not in ('submitted', 'approved')"
                            groups="site_quality_control.group_qc_quality_manager"/>
                    <button name="action_implement" string="Mark Implemented"
                            type="object" class="oe_highlight"
                            invisible="state != 'approved'"/>
                    <button name="action_verify" string="Verify &amp; Close"
                            type="object" class="oe_highlight"
                            invisible="state != 'implemented'"
                            groups="site_quality_control.group_qc_quality_manager"/>
                    <button name="action_reset_to_draft" string="Reset to Draft"
                            type="object" invisible="state not in ('rejected',)"
                            groups="site_quality_control.group_qc_quality_manager"/>
                    <field name="state" widget="statusbar"
                           statusbar_visible="draft,submitted,approved,implemented,verified"/>
                </header>
                <sheet>
                    <widget name="web_ribbon" title="Rejected" bg_color="text-bg-danger"
                            invisible="state != 'rejected'"/>
                    <div class="oe_title">
                        <label for="title"/>
                        <h1><field name="title" placeholder="Change title"/></h1>
                    </div>
                    <group>
                        <group>
                            <field name="name" readonly="1"/>
                            <field name="change_type"/>
                            <field name="date"/>
                            <field name="branch_ids" widget="many2many_tags"/>
                            <field name="requested_by_id"/>
                            <field name="company_id" groups="base.group_multi_company"/>
                        </group>
                        <group>
                            <field name="risk_level"/>
                            <field name="approved_by_id" readonly="1"/>
                            <field name="approval_date" readonly="1"/>
                            <field name="implementation_date"/>
                            <field name="implemented_by_id" readonly="1"/>
                            <field name="verification_date" readonly="1"/>
                            <field name="verification_result"/>
                        </group>
                    </group>
                    <notebook>
                        <page string="Description" name="description">
                            <group>
                                <field name="description"/>
                                <field name="reason"/>
                            </group>
                        </page>
                        <page string="Risk Assessment" name="risk">
                            <field name="risk_assessment"
                                   placeholder="Food-safety / quality impact analysis..."/>
                        </page>
                        <page string="Verification" name="verification">
                            <field name="verification_notes"/>
                        </page>
                        <page string="Rejection" name="rejection"
                              invisible="state not in ('submitted', 'approved', 'rejected')">
                            <field name="rejection_reason"
                                   placeholder="Justification required before rejecting this change..."/>
                        </page>
                        <page string="Notes" name="notes">
                            <field name="note"/>
                        </page>
                    </notebook>
                </sheet>
                <chatter/>
            </form>
        </field>
    </record>

    <record id="view_qc_change_control_list" model="ir.ui.view">
        <field name="name">qc.change.control.list</field>
        <field name="model">qc.change.control</field>
        <field name="arch" type="xml">
            <list string="Change Control"
                  decoration-danger="state == 'rejected'"
                  decoration-success="state == 'verified'">
                <field name="name"/>
                <field name="title"/>
                <field name="change_type"/>
                <field name="date"/>
                <field name="risk_level" optional="show"/>
                <field name="state" widget="badge"/>
                <field name="company_id" groups="base.group_multi_company" optional="hide"/>
            </list>
        </field>
    </record>

    <record id="view_qc_change_control_search" model="ir.ui.view">
        <field name="name">qc.change.control.search</field>
        <field name="model">qc.change.control</field>
        <field name="arch" type="xml">
            <search string="Change Control">
                <field name="name"/>
                <field name="title"/>
                <field name="change_type"/>
                <filter name="open" string="Open"
                        domain="[('state', 'not in', ('verified', 'rejected'))]"/>
                <filter name="high_risk" string="High Risk"
                        domain="[('risk_level', '=', 'high')]"/>
                <group>
                    <filter name="group_type" string="Change Type"
                            context="{'group_by': 'change_type'}"/>
                    <filter name="group_state" string="Status"
                            context="{'group_by': 'state'}"/>
                </group>
            </search>
        </field>
    </record>

    <record id="action_qc_change_control" model="ir.actions.act_window">
        <field name="name">Change Control</field>
        <field name="res_model">qc.change.control</field>
        <field name="view_mode">list,form</field>
        <field name="search_view_id" ref="view_qc_change_control_search"/>
        <field name="help" type="html">
            <p class="o_view_nocontent_smiling_face">Request a change</p>
            <p>Any planned change to a process, recipe, supplier, equipment
               or facility that could affect food safety must be risk
               assessed and approved before implementation (GMP).</p>
        </field>
    </record>

    <!-- ============================================================ -->
    <!-- Complaints                                                    -->
    <!-- ============================================================ -->
    <record id="view_qc_complaint_form" model="ir.ui.view">
        <field name="name">qc.complaint.form</field>
        <field name="model">qc.complaint</field>
        <field name="arch" type="xml">
            <form string="Quality Complaint">
                <header>
                    <button name="action_start_investigation"
                            string="Start Investigation" type="object"
                            class="oe_highlight" invisible="state != 'new'"/>
                    <button name="action_close" string="Close" type="object"
                            class="oe_highlight" invisible="state != 'investigating'"/>
                    <button name="action_reopen" string="Reopen" type="object"
                            invisible="state != 'closed'"
                            groups="site_quality_control.group_qc_quality_manager"/>
                    <field name="state" widget="statusbar"
                           statusbar_visible="new,investigating,closed"/>
                </header>
                <sheet>
                    <widget name="web_ribbon" title="Critical" bg_color="text-bg-danger"
                            invisible="severity != 'critical'"/>
                    <div class="oe_title">
                        <label for="name"/>
                        <h1><field name="name" readonly="1"/></h1>
                    </div>
                    <group>
                        <group>
                            <field name="branch_id"/>
                            <field name="date"/>
                            <field name="partner_id"/>
                            <field name="complaint_type"/>
                            <field name="severity"/>
                            <field name="company_id" groups="base.group_multi_company"/>
                        </group>
                        <group>
                            <field name="product_description"/>
                            <field name="lot_id"/>
                            <field name="lot_ref"/>
                            <field name="responsible_id"/>
                            <field name="close_date" readonly="1"/>
                            <field name="corrective_action_id" readonly="1"/>
                        </group>
                    </group>
                    <notebook>
                        <page string="Complaint" name="complaint">
                            <field name="description"/>
                        </page>
                        <page string="Investigation" name="investigation">
                            <group>
                                <field name="root_cause"/>
                                <field name="resolution"/>
                            </group>
                        </page>
                        <page string="Notes" name="notes">
                            <field name="note"/>
                        </page>
                    </notebook>
                </sheet>
                <chatter/>
            </form>
        </field>
    </record>

    <record id="view_qc_complaint_list" model="ir.ui.view">
        <field name="name">qc.complaint.list</field>
        <field name="model">qc.complaint</field>
        <field name="arch" type="xml">
            <list string="Quality Complaints"
                  decoration-danger="severity in ('high', 'critical')"
                  decoration-success="state == 'closed'">
                <field name="name"/>
                <field name="branch_id"/>
                <field name="date"/>
                <field name="complaint_type"/>
                <field name="severity" widget="badge"
                       decoration-danger="severity in ('high', 'critical')"
                       decoration-warning="severity == 'medium'"/>
                <field name="responsible_id" optional="show"/>
                <field name="state" widget="badge"/>
                <field name="company_id" groups="base.group_multi_company" optional="hide"/>
            </list>
        </field>
    </record>

    <record id="view_qc_complaint_search" model="ir.ui.view">
        <field name="name">qc.complaint.search</field>
        <field name="model">qc.complaint</field>
        <field name="arch" type="xml">
            <search string="Quality Complaints">
                <field name="name"/>
                <field name="branch_id"/>
                <field name="partner_id"/>
                <filter name="open" string="Open"
                        domain="[('state', '!=', 'closed')]"/>
                <filter name="critical" string="Critical / High"
                        domain="[('severity', 'in', ('critical', 'high'))]"/>
                <group>
                    <filter name="group_branch" string="Site"
                            context="{'group_by': 'branch_id'}"/>
                    <filter name="group_type" string="Type"
                            context="{'group_by': 'complaint_type'}"/>
                    <filter name="group_state" string="Status"
                            context="{'group_by': 'state'}"/>
                </group>
            </search>
        </field>
    </record>

    <record id="action_qc_complaint" model="ir.actions.act_window">
        <field name="name">Complaints</field>
        <field name="res_model">qc.complaint</field>
        <field name="view_mode">list,form</field>
        <field name="search_view_id" ref="view_qc_complaint_search"/>
        <field name="help" type="html">
            <p class="o_view_nocontent_smiling_face">Log a complaint</p>
            <p>Customer and internal quality complaints, investigated to a
               documented root cause and resolution. Critical or
               allergen-related complaints raise a corrective action
               automatically.</p>
        </field>
    </record>

    <!-- ============================================================ -->
    <!-- Product hold / quarantine                                    -->
    <!-- ============================================================ -->
    <record id="view_qc_product_hold_form" model="ir.ui.view">
        <field name="name">qc.product.hold.form</field>
        <field name="model">qc.product.hold</field>
        <field name="arch" type="xml">
            <form string="Product Hold">
                <header>
                    <button name="action_release" string="Release" type="object"
                            class="oe_highlight" invisible="status != 'on_hold'"
                            groups="site_quality_control.group_qc_quality_manager"/>
                    <button name="action_dispose" string="Dispose" type="object"
                            invisible="status != 'on_hold'"
                            groups="site_quality_control.group_qc_quality_manager"/>
                    <button name="action_reopen" string="Reopen" type="object"
                            invisible="status == 'on_hold'"
                            groups="site_quality_control.group_qc_quality_manager"/>
                    <field name="status" widget="statusbar"
                           statusbar_visible="on_hold,released"/>
                </header>
                <sheet>
                    <widget name="web_ribbon" title="On Hold" bg_color="text-bg-danger"
                            invisible="status != 'on_hold'"/>
                    <widget name="web_ribbon" title="Disposed" bg_color="text-bg-warning"
                            invisible="status != 'disposed'"/>
                    <div class="oe_title">
                        <label for="name"/>
                        <h1><field name="name" readonly="1"/></h1>
                    </div>
                    <group>
                        <group>
                            <field name="branch_id"/>
                            <field name="date_held"/>
                            <field name="product_description"/>
                            <field name="lot_id"/>
                            <field name="lot_ref"/>
                            <field name="qty_held"/>
                            <field name="uom_name"/>
                            <field name="company_id" groups="base.group_multi_company"/>
                        </group>
                        <group>
                            <field name="hold_type"/>
                            <field name="initiated_by_id"/>
                            <field name="recall_id"/>
                            <field name="released_by_id" readonly="1"/>
                            <field name="release_date" readonly="1"/>
                            <field name="disposal_method"
                                   readonly="status != 'on_hold'"/>
                        </group>
                    </group>
                    <group string="Reason">
                        <field name="reason" nolabel="1"/>
                    </group>
                    <group string="Release / Disposition Justification">
                        <field name="release_reason" nolabel="1"
                               readonly="status != 'on_hold'"
                               placeholder="Justification required before releasing or disposing of this hold..."/>
                    </group>
                    <field name="note" placeholder="Notes..."/>
                </sheet>
                <chatter/>
            </form>
        </field>
    </record>

    <record id="view_qc_product_hold_list" model="ir.ui.view">
        <field name="name">qc.product.hold.list</field>
        <field name="model">qc.product.hold</field>
        <field name="arch" type="xml">
            <list string="Product Holds"
                  decoration-danger="status == 'on_hold'"
                  decoration-muted="status == 'disposed'"
                  decoration-success="status == 'released'">
                <field name="name"/>
                <field name="branch_id"/>
                <field name="date_held"/>
                <field name="product_description"/>
                <field name="hold_type"/>
                <field name="qty_held" optional="show"/>
                <field name="status" widget="badge"
                       decoration-danger="status == 'on_hold'"
                       decoration-success="status == 'released'"
                       decoration-muted="status == 'disposed'"/>
                <field name="company_id" groups="base.group_multi_company" optional="hide"/>
            </list>
        </field>
    </record>

    <record id="view_qc_product_hold_search" model="ir.ui.view">
        <field name="name">qc.product.hold.search</field>
        <field name="model">qc.product.hold</field>
        <field name="arch" type="xml">
            <search string="Product Holds">
                <field name="name"/>
                <field name="branch_id"/>
                <field name="product_description"/>
                <filter name="on_hold" string="On Hold"
                        domain="[('status', '=', 'on_hold')]"/>
                <group>
                    <filter name="group_branch" string="Site"
                            context="{'group_by': 'branch_id'}"/>
                    <filter name="group_type" string="Hold Type"
                            context="{'group_by': 'hold_type'}"/>
                    <filter name="group_status" string="Status"
                            context="{'group_by': 'status'}"/>
                </group>
            </search>
        </field>
    </record>

    <record id="action_qc_product_hold" model="ir.actions.act_window">
        <field name="name">Product Holds</field>
        <field name="res_model">qc.product.hold</field>
        <field name="view_mode">list,form</field>
        <field name="search_view_id" ref="view_qc_product_hold_search"/>
        <field name="help" type="html">
            <p class="o_view_nocontent_smiling_face">Place product on hold</p>
            <p>Non-conforming or suspect product held pending investigation,
               then released or disposed of by a Quality Manager (GMP
               control of nonconforming product).</p>
        </field>
    </record>

</odoo>
