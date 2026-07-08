# -*- coding: utf-8 -*-

def migrate(cr, version):
    cr.execute("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = 'res_company'
          AND column_name = 'attendance_geo_latitude'
    """)
    if not cr.fetchone():
        return

    cr.execute("""
        SELECT EXISTS (
            SELECT 1
            FROM information_schema.tables
            WHERE table_name = 'res_company_geofence_location'
        )
    """)
    if not cr.fetchone()[0]:
        cr.execute("""
            CREATE TABLE res_company_geofence_location (
                id SERIAL PRIMARY KEY,
                company_id INTEGER NOT NULL REFERENCES res_company(id) ON DELETE CASCADE,
                sequence INTEGER,
                name VARCHAR,
                latitude DOUBLE PRECISION,
                longitude DOUBLE PRECISION,
                radius_m DOUBLE PRECISION,
                create_uid INTEGER REFERENCES res_users(id) ON DELETE SET NULL,
                write_uid INTEGER REFERENCES res_users(id) ON DELETE SET NULL,
                create_date TIMESTAMP WITHOUT TIME ZONE,
                write_date TIMESTAMP WITHOUT TIME ZONE
            )
        """)
        cr.execute("""
            CREATE INDEX res_company_geofence_location_company_id_index
            ON res_company_geofence_location (company_id)
        """)

    cr.execute("""
        SELECT c.id, c.attendance_geo_latitude, c.attendance_geo_longitude, c.attendance_geo_radius_m
        FROM res_company c
        WHERE c.attendance_geo_enforce = TRUE
          AND c.attendance_geo_latitude IS NOT NULL
          AND c.attendance_geo_longitude IS NOT NULL
          AND NOT EXISTS (
              SELECT 1
              FROM res_company_geofence_location g
              WHERE g.company_id = c.id
          )
    """)
    for company_id, latitude, longitude, radius_m in cr.fetchall():
        cr.execute("""
            INSERT INTO res_company_geofence_location (
                company_id, sequence, name, latitude, longitude, radius_m,
                create_uid, write_uid, create_date, write_date
            )
            VALUES (%s, 10, 'Main Location', %s, %s, %s, 1, 1, NOW() AT TIME ZONE 'UTC', NOW() AT TIME ZONE 'UTC')
        """, (
            company_id,
            latitude,
            longitude,
            radius_m or 200.0,
        ))
