# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging

import odoo.exceptions
import odoo.tools
from odoo import http, _
from odoo.addons.auth_signup.controllers.main import AuthSignupHome
from odoo.addons.web.controllers.home import ensure_db, SIGN_UP_REQUEST_PARAMS
from odoo.exceptions import AccessDenied, UserError
from odoo.http import request

try:
    from odoo.addons.remember_device_login.controllers.remember_device_login import RememberDeviceHome
except ImportError:
    RememberDeviceHome = AuthSignupHome

_logger = logging.getLogger(__name__)


class ForcePasswordChangeHome(RememberDeviceHome):

    def _get_wsgienv(self):
        return {
            'interactive': True,
            'base_location': request.httprequest.url_root.rstrip('/'),
            'HTTP_HOST': request.httprequest.environ['HTTP_HOST'],
            'REMOTE_ADDR': request.httprequest.remote_addr,
        }

    def _verify_login_credentials(self, credential):
        Users = request.env['res.users'].sudo()
        with Users._assert_can_auth(user=credential['login']):
            user = Users.search(
                Users._get_login_domain(credential['login']),
                order=Users._get_login_order(),
                limit=1,
            )
            if not user:
                _logger.info(
                    "auth_force_password_change: no user found for login=%r",
                    credential.get('login'),
                )
                raise AccessDenied()
            user = user.with_user(user).sudo()
            user._check_credentials(credential, self._get_wsgienv())
        return user

    def _log_user_password_reset_state(self, user, stage):
        log_count = len(user.log_ids)
        must_change = user.must_change_password
        must_reset = user.must_reset_password_on_login()
        _logger.info(
            "auth_force_password_change [%s]: user_id=%s login=%r "
            "must_change_password=%s log_ids_count=%s must_reset_password_on_login=%s",
            stage,
            user.id,
            user.login,
            must_change,
            log_count,
            must_reset,
        )
        return must_reset

    def _start_force_change_password_session(self, user, login):
        request.session['pre_uid'] = user.id
        request.session['pre_login'] = login
        request.session['force_change_password'] = True
        _logger.info(
            "auth_force_password_change: started force-change session for user_id=%s login=%r",
            user.id,
            login,
        )

    def _clear_force_change_password_session(self):
        request.session.pop('force_change_password', None)
        _logger.info("auth_force_password_change: cleared force-change session")

    def _is_force_change_password_flow(self):
        active = bool(request.session.get('force_change_password') and request.session.get('pre_uid'))
        if active:
            _logger.info(
                "auth_force_password_change: active force-change flow pre_uid=%s pre_login=%r",
                request.session.get('pre_uid'),
                request.session.get('pre_login'),
            )
        return active

    def _render_force_change_password(self, redirect=None, **kw):
        values = {k: v for k, v in request.params.items() if k in SIGN_UP_REQUEST_PARAMS}
        values.update(self.get_auth_signup_config())
        values['force_change_password'] = True
        values['login'] = request.session.get('pre_login', '')
        values['redirect'] = redirect or values.get('redirect')
        if not odoo.tools.config['list_db']:
            values['disable_database_manager'] = True
        _logger.info(
            "auth_force_password_change: rendering force-change section login=%r redirect=%r",
            values.get('login'),
            values.get('redirect'),
        )
        response = request.render('web.login', values)
        response.headers['Cache-Control'] = 'no-cache'
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['Content-Security-Policy'] = "frame-ancestors 'self'"
        return response

    def _complete_force_change_password(self, new_password, redirect=None):
        uid = request.session.get('pre_uid')
        login = request.session.get('pre_login')
        _logger.info(
            "auth_force_password_change: completing password change pre_uid=%s pre_login=%r",
            uid,
            login,
        )
        if not uid or not login:
            raise AccessDenied()

        user = request.env['res.users'].sudo().browse(uid)
        if not user.exists() or not user.active:
            raise AccessDenied()
        if not user.must_reset_password_on_login():
            _logger.warning(
                "auth_force_password_change: user_id=%s no longer requires password reset",
                user.id,
            )
            raise AccessDenied()

        new_password = (new_password or '').strip()
        if not new_password:
            raise UserError(_("Setting empty passwords is not allowed for security reasons!"))

        user.with_context(auth_force_password_change_done=True).write({
            'password': new_password,
            'must_change_password': False,
        })
        _logger.info(
            "auth_force_password_change: password updated for user_id=%s login=%r",
            user.id,
            login,
        )
        self._clear_force_change_password_session()

        credential = {'login': login, 'password': new_password, 'type': 'password'}
        if request.env['res.users']._should_captcha_login(credential):
            request.env['ir.http']._verify_request_recaptcha_token('login')
        request.session.authenticate(request.env, credential)
        request.params['login_success'] = True
        request.params['password'] = new_password
        if request.session.uid:
            return request.redirect(self._login_redirect(request.session.uid, redirect=redirect))
        mfa_url = user._mfa_url()
        if mfa_url:
            return request.redirect_query(mfa_url, query={'redirect': redirect} if redirect else {})
        return request.redirect(self._login_redirect(uid, redirect=redirect))

    @http.route()
    def web_login(self, redirect=None, **kw):
        ensure_db()
        _logger.info(
            "auth_force_password_change web_login: method=%s login=%r has_new_password=%s "
            "session_uid=%s force_change_session=%s",
            request.httprequest.method,
            request.params.get('login'),
            bool(request.params.get('new_password')),
            request.session.uid,
            request.session.get('force_change_password'),
        )

        if self._is_force_change_password_flow():
            if request.httprequest.method == 'POST':
                try:
                    return self._complete_force_change_password(
                        request.params.get('new_password'),
                        redirect=redirect,
                    )
                except AccessDenied:
                    self._clear_force_change_password_session()
                    request.session.logout(keep_db=True)
                    return request.redirect('/web/login?error=access')
                except UserError as exc:
                    response = self._render_force_change_password(redirect=redirect, **kw)
                    response.qcontext['error'] = exc.args[0]
                    return response
                except odoo.exceptions.AccessDenied as exc:
                    response = self._render_force_change_password(redirect=redirect, **kw)
                    if exc.args == AccessDenied().args:
                        response.qcontext['error'] = _("Wrong login/password")
                    else:
                        response.qcontext['error'] = exc.args[0]
                    return response
            return self._render_force_change_password(redirect=redirect, **kw)

        if request.httprequest.method == 'POST' and not request.params.get('new_password'):
            credential = {
                key: value
                for key, value in request.params.items()
                if key in ('login', 'password', 'type') and value
            }
            credential.setdefault('type', 'password')
            if credential.get('login') and credential.get('password'):
                try:
                    if request.env['res.users']._should_captcha_login(credential):
                        request.env['ir.http']._verify_request_recaptcha_token('login')
                    user = self._verify_login_credentials(credential)
                    if self._log_user_password_reset_state(user, 'after_credential_check'):
                        self._start_force_change_password_session(user, credential['login'])
                        return self._render_force_change_password(redirect=redirect, **kw)
                    _logger.info(
                        "auth_force_password_change: skipping force-change for user_id=%s login=%r, "
                        "delegating to standard login",
                        user.id,
                        user.login,
                    )
                except AccessDenied as exc:
                    _logger.info(
                        "auth_force_password_change: credential check failed for login=%r (%s)",
                        credential.get('login'),
                        exc.args[0] if exc.args else 'AccessDenied',
                    )

        return super().web_login(redirect=redirect, **kw)
