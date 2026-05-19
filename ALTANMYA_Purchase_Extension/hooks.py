SYSTEM_STAGES = [
    {'code': 'draft', 'name': 'RFQ', 'stageorder': -20, 'issystem': True},
    {'code': 'sent', 'name': 'Sent Sent', 'stageorder': -10, 'issystem': True},
    {'code': 'to approve', 'name': 'To Approve', 'stageorder': -5, 'issystem': True},
    {'code': 'purchase', 'name': 'Purchase Order', 'stageorder': 1000, 'issystem': True},
    {'code': 'done', 'name': 'Locked', 'stageorder': 1100, 'issystem': True},
    {'code': 'cancel', 'name': 'Cancelled', 'stageorder': 1200, 'issystem': True},
]

def test_post_init_hook(env):
    stage_model = env['tanmya.purchase.stage'].sudo()
    for values in SYSTEM_STAGES:
        if not stage_model.search([('code', '=', values['code'])], limit=1):
            stage_model.create(values)


    env.cr.execute(""" DROP SEQUENCE IF EXISTS seq_tanmia_pstage_users
    """)
    env.cr.execute(""" CREATE SEQUENCE seq_tanmia_pstage_users INCREMENT 1 START 1
    """)
    env.cr.execute(""" ALTER TABLE IF EXISTS res_users_tanmya_purchase_stage_rel
    ADD COLUMN seq integer DEFAULT nextval('seq_tanmia_pstage_users'::regclass)
    """)


