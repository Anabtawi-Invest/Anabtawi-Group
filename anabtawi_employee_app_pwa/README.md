Employee App PWA 19.0.1.1.4

Static paths flattened to avoid Windows path-too-long extraction errors.


## 19.0.1.1.6
Based on the working 19.0.1.1.4 package.
Changes added without changing the working route/static structure:
- Hidden from Odoo Apps launcher; URL-only at /employee-portal.
- Mobile browser RTL/LTR stability fix.
- Arabic body direction fix.
- Added body dir sync when language changes.
- Service worker cache bumped.
- Profile image can use Odoo profile image URL when API returns it.


## 19.0.1.1.7
- Restored application=True so Odoo Apps can find and upgrade the module.
- Kept Employee App hidden from normal users using base.group_no_one instead of disabling the application.
- Added support for both /employee-portal and /employee-portal/ routes.
- Added sitemap=False to public PWA routes.


## 19.0.1.1.8
Mobile Arabic fix: keeps global document direction LTR to prevent React Native Web / iOS PWA horizontal clipping while Arabic labels remain handled by the app language layer.
