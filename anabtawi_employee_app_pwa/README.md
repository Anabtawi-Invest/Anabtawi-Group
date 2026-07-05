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
