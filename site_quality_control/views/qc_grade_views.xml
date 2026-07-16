<?xml version="1.0" encoding="utf-8"?>
<odoo>

    <record id="view_qc_grade_list" model="ir.ui.view">
        <field name="name">qc.grade.list</field>
        <field name="model">qc.grade</field>
        <field name="arch" type="xml">
            <list string="Grades" editable="bottom">
                <field name="sequence" widget="handle"/>
                <field name="letter"/>
                <field name="name"/>
                <field name="classification"/>
                <field name="min_score"/>
                <field name="max_score"/>
                <field name="color" widget="color_picker" optional="hide"/>
            </list>
        </field>
    </record>

    <record id="view_qc_grade_form" model="ir.ui.view">
        <field name="name">qc.grade.form</field>
        <field name="model">qc.grade</field>
        <field name="arch" type="xml">
            <form string="Grade">
                <sheet>
                    <group>
                        <group>
                            <field name="letter"/>
                            <field name="name"/>
                            <field name="classification"/>
                        </group>
                        <group>
                            <field name="min_score"/>
                            <field name="max_score"/>
                            <field name="sequence"/>
                            <field name="color" widget="color_picker"/>
                        </group>
                    </group>
                </sheet>
            </form>
        </field>
    </record>

    <record id="action_qc_grade" model="ir.actions.act_window">
        <field name="name">Grades</field>
        <field name="res_model">qc.grade</field>
        <field name="view_mode">list,form</field>
    </record>

</odoo>
