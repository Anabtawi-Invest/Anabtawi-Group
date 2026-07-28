def migrate(cr, version):
    cr.execute("""
        UPDATE res_partner p
        SET employee_number = sub.employee_number
        FROM (
            SELECT DISTINCT ON (p.id, e.company_id)
                p.id AS partner_id,
                e.employee_number
            FROM res_partner p
            JOIN hr_employee e ON e.work_contact_id = p.id
            WHERE e.employee_number IS NOT NULL
            ORDER BY p.id, e.company_id
        ) sub
        WHERE p.id = sub.partner_id
    """)
    cr.execute("""
        UPDATE res_partner p
        SET employee_number = sub.employee_number
        FROM (
            SELECT DISTINCT ON (p.id, e.company_id)
                p.id AS partner_id,
                e.employee_number
            FROM res_partner p
            JOIN hr_employee e ON e.work_contact_id IS NULL
            JOIN resource_resource r ON r.id = e.resource_id
            JOIN res_users u ON u.id = r.user_id AND u.partner_id = p.id
            WHERE e.employee_number IS NOT NULL
            ORDER BY p.id, e.company_id
        ) sub
        WHERE p.id = sub.partner_id
          AND (p.employee_number IS NULL OR p.employee_number = '')
    """)
