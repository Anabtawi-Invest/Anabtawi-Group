# -*- coding: utf-8 -*-

from odoo.http import content_disposition, Controller, request, route
from odoo.addons.account.controllers.portal import CustomerPortal
from odoo import fields, http, SUPERUSER_ID, _
from odoo.tools import groupby as groupbyelem
from operator import itemgetter
import re
from odoo.addons.portal.controllers.portal import pager as portal_pager
from odoo.tools import date_utils
import base64
from dateutil.relativedelta import relativedelta
import logging

_logger = logging.getLogger(__name__)


class EmployeePortal(CustomerPortal):
    _items_per_page = 80

    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        user = request.env.user
        employee = request.env['hr.employee'].sudo().search([('user_id', '=', user.id)])
        user = request.env.user

        Leave = request.env['hr.leave'].sudo()

        _logger.info(
            "Portal leave home values: user_id=%s login=%s employee_id=%s employee_company_id=%s counters=%s",
            user.id,
            user.login,
            employee.id if employee else False,
            employee.company_id.id if employee else False,
            counters,
        )

        if 'leave_count' in counters:
            values['leave_count'] = Leave.search_count(self._prepare_leaves_domain(employee))
        if 'request_count' in counters:
            values['request_count'] = Leave.search_count(self._prepare_requests_domain(user))
        _logger.info(
            "Portal leave home counters resolved: user_id=%s leave_count=%s request_count=%s",
            user.id,
            values.get('leave_count'),
            values.get('request_count'),
        )
        return values

    def _prepare_leaves_domain(self, employee):
        return [
            ('employee_id', '=', employee.id),
        ]

    def _prepare_requests_domain(self, user):
        return [
            '&',
            ('state', 'in', ['confirm']),
            ('current_approver', '=', user.id)
        ]

    def _prepare_leaves_portal_rendering_values(self, sortby=None, groupby='none', filterby='all', search=None, search_in='content', page=1, manager=False, **kwargs):
        Leave = request.env['hr.leave'].sudo()
        user = request.env.user
        employee = request.env['hr.employee'].sudo().search([('user_id', '=', user.id)])
        values = self._prepare_portal_layout_values()
        searchbar_sortings = {
            'date_from': {'label': _('Newest'), 'order': 'date_from desc'},
            'state': {'label': _('State'), 'order': 'state desc'},
            'holiday_status_id': {'label': _('Time Off Type'), 'order': 'holiday_status_id desc'},

        }
        searchbar_inputs = {
            'name': {'input': 'name', 'label': _('Search In Description')},
        }
        today = fields.Date.today()
        quarter_start, quarter_end = date_utils.get_quarter(today)
        last_week = today + relativedelta(weeks=-1)
        last_month = today + relativedelta(months=-1)
        last_year = today + relativedelta(years=-1)
        searchbar_filters = {
            'all': {'label': _('All'), 'domain': []},
            'today': {'label': _('Today'), 'domain': [("request_date_from", "=", today)]},
            'week': {'label': _('This week'),
                     'domain': [('request_date_from', '>=', date_utils.start_of(today, "week")),
                                ('request_date_from', '<=', date_utils.end_of(today, 'week'))]},
            'month': {'label': _('This month'),
                      'domain': [('request_date_from', '>=', date_utils.start_of(today, 'month')),
                                 ('request_date_from', '<=', date_utils.end_of(today, 'month'))]},
            'year': {'label': _('This year'),
                     'domain': [('request_date_from', '>=', date_utils.start_of(today, 'year')),
                                ('request_date_from', '<=', date_utils.end_of(today, 'year'))]},
            'quarter': {'label': _('This Quarter'),
                        'domain': [('request_date_from', '>=', quarter_start),
                                   ('request_date_from', '<=', quarter_end)]},
            'last_week': {'label': _('Last week'),
                          'domain': [('request_date_from', '>=', date_utils.start_of(last_week, "week")),
                                     ('request_date_from', '<=', date_utils.end_of(last_week, 'week'))]},
            'last_month': {'label': _('Last month'),
                           'domain': [('request_date_from', '>=', date_utils.start_of(last_month, 'month')),
                                      ('request_date_from', '<=', date_utils.end_of(last_month, 'month'))]},
            'last_year': {'label': _('Last year'),
                          'domain': [('request_date_from', '>=', date_utils.start_of(last_year, 'year')),
                                     ('request_date_from', '<=', date_utils.end_of(last_year, 'year'))]},
        }
        searchbar_groupby = {
            'none': {'label': _('None'), 'input': 'none'},
            'state': {'label': _('Stage'), 'input': 'state'},
            'holiday_status_id': {'label': _('Leave Type'), 'input': 'holiday_status_id'},
        }

        groupby_mapping = self._leave_get_groupby_mapping()
        groupby_field = groupby_mapping.get(groupby, None)

        if groupby_field is not None and groupby_field not in Leave._fields:
            raise ValueError(_("The field '%s' does not exist in the targeted model", groupby_field))

        if not manager:
            searchbar_filters.update({
                'draft': {'label': _('Draft'), 'domain': [('state', '=', 'draft')]},
                'confirm': {'label': _('Confirmed'), 'domain': [('state', '=', 'confirm')]},
                'validate': {'label': _('Approved'), 'domain': [('state', '=', 'validate')]},
                'refuse': {'label': _('Refused'), 'domain': [('state', '=', 'refuse')]}, })
        if not sortby:
            sortby = 'date_from'
        sort_order = searchbar_sortings[sortby]['order']
        order = '%s, %s' % (groupby_field, sort_order) if groupby_field else sort_order

        url = "/my/leaves" if not manager else '/my/requests'
        domain = self._prepare_leaves_domain(employee) if not manager else self._prepare_requests_domain(user)
        domain += searchbar_filters[filterby]['domain']

        pager_values = portal_pager(
            url=url,
            url_args={'sortby': sortby, 'search_in': search_in, 'search': search, 'groupby': groupby},
            total=Leave.search_count(domain),
            page=page,
            step=self._items_per_page,
        )
        if search:
            search_domain = [('private_name', 'ilike', search)]
            domain += search_domain

        leave = Leave.search(domain, order=order, limit=self._items_per_page, offset=pager_values['offset'])
        page_name = 'leave' if not manager else 'leave_requests'

        if groupby_field:
            grouped_leaves = [Leave.concat(*g) for k, g in groupbyelem(leave, itemgetter(searchbar_groupby[groupby]['input']))]
        else:
            grouped_leaves = [leave]
        values.update({
            'leaves': leave.sudo(),
            'page_name': page_name,
            'pager': pager_values,
            'grouped_leaves': grouped_leaves,
            'searchbar_sortings': searchbar_sortings,
            'searchbar_filters': searchbar_filters,
            'searchbar_groupby': searchbar_groupby,
            'searchbar_inputs': searchbar_inputs,
            'groupby': groupby,
            'sortby': sortby,
            'search_in': search_in,
            'search': search,
            'user': request.env.user,
            'filterby': filterby,
            'default_url': url,
        })

        return values

    def _leave_get_groupby_mapping(self):
        return {
            'state': 'state',
            'holiday_status_id': 'holiday_status_id',
        }

    def _get_portal_timeoff_types(self, employee):
        if not employee:
            return []
        return request.env['hr.leave.type'].sudo().with_company(employee.company_id).with_context(
            employee_id=employee.id,
            allowed_company_ids=[employee.company_id.id],
        ).get_allocation_data_request(hidden_allocations=False)

    def _get_portal_selectable_leave_types(self, employee):
        """Same selection rules as the backend time off form (hr_leave_views holiday_status_id domain)."""
        if not employee:
            return request.env['hr.leave.type'].browse()
        LeaveType = request.env['hr.leave.type'].sudo().with_company(employee.company_id).with_context(
            employee_id=employee.id,
            default_employee_id=employee.id,
            allowed_company_ids=[employee.company_id.id],
        )
        domain = [
            '&',
            '|',
            ('company_id', '=', False),
            ('company_id', '=', employee.company_id.id),
            '|',
            ('requires_allocation', '=', False),
            '&',
            ('has_valid_allocation', '=', True),
            '|',
            ('allows_negative', '=', True),
            '&',
            ('virtual_remaining_leaves', '>', 0),
            ('allows_negative', '=', False),
        ]
        return LeaveType.search(domain, order='sequence')

    def _prepare_featured_timeoff_balances(self, timeoff_types):
        def _normalize_name(name):
            return (name or '').strip().lower()

        def _match_timeoff(keywords, *, request_unit=None):
            for timeoff in timeoff_types:
                name = _normalize_name(timeoff[0])
                data = timeoff[1]
                if request_unit and data.get('request_unit') != request_unit:
                    continue
                if any(keyword in name for keyword in keywords):
                    return timeoff
            return None

        def _serialize_balance(default_title, theme, timeoff):
            data = timeoff[1] if timeoff else {}
            request_unit = data.get('request_unit') or 'day'
            unit_label = _('Hours') if request_unit == 'hour' else _('Days')
            unit_short = _('Hrs') if request_unit == 'hour' else _('Days')
            return {
                'label': default_title,
                'display_name': timeoff[0] if timeoff else default_title,
                'available': round(data.get('virtual_remaining_leaves', 0.0), 2),
                'total': round(data.get('max_leaves', 0.0), 2),
                'used': round(data.get('virtual_leaves_taken', 0.0), 2),
                'unit_label': unit_label,
                'unit_short': unit_short,
                'theme': theme,
                'missing': not bool(timeoff),
            }

        annual_leave = _match_timeoff(['annual', 'vacation'], request_unit='day')
        extra_hours = _match_timeoff(['extra', 'overtime'], request_unit='hour')
        if not extra_hours:
            extra_hours = _match_timeoff(['extra', 'overtime', 'hour'], request_unit='hour')

        return [
            _serialize_balance(_('Annual Leave'), 'annual', annual_leave),
            _serialize_balance(_('Extra Hours'), 'extra', extra_hours),
        ]

    @http.route(['/my/leaves', '/my/leaves/page/<int:page>'], type='http', auth="user", website=True)
    def portal_my_leaves(self, sortby=None, groupby='none', filterby='all', search=None, search_in='content', page=1, **kwargs):
        values = self._prepare_leaves_portal_rendering_values(sortby, groupby, filterby, search,
                                                              search_in, page, False, **kwargs)
        employee = request.env['hr.employee'].sudo().search([('user_id', '=', request.env.user.id)])
        timeoffs = request.env['hr.leave.type'].sudo()
        timeoff_types = []
        if employee:
            timeoff_types = self._get_portal_timeoff_types(employee)
            timeoffs = request.env['hr.leave.type'].sudo().browse([timeoff[3] for timeoff in timeoff_types])
        featured_timeoff_balances = self._prepare_featured_timeoff_balances(timeoff_types)
        _logger.info(
            "Portal my leaves page: user_id=%s employee_id=%s employee_company_id=%s leaves_count=%s "
            "raw_timeoff_type_ids=%s rendered_timeoff_types_count=%s rendered_timeoff_type_names=%s",
            request.env.user.id,
            employee.id if employee else False,
            employee.company_id.id if employee else False,
            len(values.get('leaves', [])),
            timeoffs.ids,
            len(timeoff_types),
            [timeoff[0] for timeoff in timeoff_types],
        )
        if not employee:
            _logger.warning(
                "Portal my leaves page without linked employee: user_id=%s login=%s",
                request.env.user.id,
                request.env.user.login,
            )
        elif not timeoff_types:
            _logger.warning(
                "Portal my leaves page has no requestable leave types: user_id=%s employee_id=%s company_id=%s "
                "raw_timeoff_type_ids=%s",
                request.env.user.id,
                employee.id,
                employee.company_id.id,
                timeoffs.ids,
            )
        values['timeoff_types'] = timeoff_types
        values['featured_timeoff_balances'] = featured_timeoff_balances
        leaves = values['leaves']
        request.session['my_leaves_history'] = leaves.ids[:100]
        return request.render("portal_leaves.portal_my_leaves", values)

    @http.route(['/my/requests', '/my/requests/page/<int:page>'], type='http', auth="user", website=True)
    def portal_my_requests(self, sortby=None, groupby='none', filterby='all', search=None, search_in='content', page=1, **kwargs):
        values = self._prepare_leaves_portal_rendering_values(sortby, groupby, filterby, search,
                                                              search_in, page, True, **kwargs)
        values['page_name'] = 'leave_requests'
        leave_requests = values['leaves']
        request.session['my_requests_history'] = leave_requests.ids[:100]
        return request.render("portal_leaves.portal_my_requests", values)

    def request_name_get(self, requests):
        return [(request.id, request.display_name) for request in requests]

    @http.route(['/my/leaves/request'], type='http', auth="user", website=True)
    def my_timeoff_request_form(self, access_token=None, **post):
        values = {}
        employee = request.env['hr.employee'].sudo().search([('user_id', '=', request.env.user.id)])
        _logger.info(
            "Portal leave request form opened: user_id=%s login=%s method=%s employee_id=%s employee_company_id=%s post_keys=%s",
            request.env.user.id,
            request.env.user.login,
            request.httprequest.method,
            employee.id if employee else False,
            employee.company_id.id if employee else False,
            sorted(post.keys()),
        )
        if employee:
            timeoffs = self._get_portal_selectable_leave_types(employee)
            timeoff_types = self.request_name_get(timeoffs)
            day_hours = employee.resource_calendar_id.hours_per_day / 2 if employee.resource_calendar_id else 0
            _logger.info(
                "Portal leave request form options: user_id=%s employee_id=%s company_id=%s calendar_id=%s "
                "matched_timeoff_type_ids=%s matched_timeoff_type_names=%s hidden_filter=%s half_day_hours=%s",
                request.env.user.id,
                employee.id,
                employee.company_id.id,
                employee.resource_calendar_id.id if employee.resource_calendar_id else False,
                timeoffs.ids,
                timeoffs.mapped('name'),
                "backend_form_domain",
                day_hours,
            )
            if not timeoff_types:
                _logger.warning(
                    "Portal leave request form has no selectable leave types: user_id=%s employee_id=%s company_id=%s",
                    request.env.user.id,
                    employee.id,
                    employee.company_id.id,
                )
        else:
            timeoff_types = []
            day_hours = 0
            _logger.warning(
                "Portal leave request form blocked because user has no linked employee: user_id=%s login=%s",
                request.env.user.id,
                request.env.user.login,
            )
        if post and request.httprequest.method == 'POST':
            message = self.my_timeoff_request_create(**post)
            leave = message.get('leave')
            if message.get('error'):
                values = {'error': message.get('error'),
                          'create_leave': False,
                          'timeoff_types': timeoff_types,
                          'half_day_hours': day_hours,
                          'employee': employee,
                          'employee_id': employee.id,
                          'page_name': 'create_request',
                          }
                return request.render("portal_leaves.portal_timeoff_request_form", values)
            elif leave:
                url = leave.get_portal_url()
                return request.redirect(url)
        values.update({
            'error': {},
            'create_leave': True,
            'timeoff_types': timeoff_types,
            'half_day_hours': day_hours,
            'employee': employee,
            'employee_id': employee.id,
            'page_name': 'create_request',
        })
        return request.render("portal_leaves.portal_timeoff_request_form", values)

    @http.route('/web/binary/download_document/<int:id>', type='http', auth="user")
    def download_document(self, id, **kwargs):
        def remove_duplicate_extensions(filename):
            pattern = re.compile(r'(\.[a-zA-Z0-9]+)\1+')
            result = re.sub(pattern, r'\1', filename)
            return result

        attachment = request.env['ir.attachment'].sudo().browse(int(id))
        file = base64.b64decode(attachment.datas)
        file_type_index = attachment.mimetype.rfind('/')
        file_type = attachment.mimetype[file_type_index + 1:]
        file_name = f'{attachment.name}.{file_type}'.replace(' ', '')
        return request.make_response(file, [('Content-Type', 'text/plain'),
                                            ('Content-Disposition',
                                             content_disposition(remove_duplicate_extensions(file_name)))])

    def time_to_float(self, time_str):
        hours, minutes = map(int, time_str.split(':'))

        return hours + minutes / 60.0

    def my_timeoff_request_create(self, **post):
        safe_post = {key: val for key, val in post.items() if key != 'document'}
        values = {}
        values['holiday_status_id'] = int(post['holiday_status_id'])
        values['employee_id'] = int(post['employee_id'])
        values['date_from'] = post['date_from']
        values['date_to'] = post['date_to']
        values['name'] = post['name']
        values['request_unit_half'] = False
        values['request_unit_hours'] = False
        if post['request_unit'] == 'hours':
            hour_to = self.time_to_float(post['request_hour_to'])
            hour_from = self.time_to_float(post['request_hour_from'])
            values['date_from'] = post['date_from']
            values['date_to'] = post['date_to']
            values['request_date_from'] = post['date_from']
            values['request_date_to'] = post['date_to']
            values['request_unit_hours'] = True
            values['request_unit_half'] = False
            values['request_hour_from'] = hour_from
            values['request_hour_to'] = hour_to
            if float(hour_to) <= float(hour_from):
                values['error'] = _("The start date must be anterior to the end date")
                return values

        elif post['request_unit'] == 'half_day':
            values['request_unit_half'] = True
            values['request_date_from_period'] = post['request_date_from_period']
            values['request_unit_half'] = True
            values['request_unit_hours'] = False
            values['request_date_from'] = post['date_from']
            values['request_date_to'] = post['date_to']

        else:
            values['request_date_from'] = post['date_from']
            values['request_date_to'] = post['date_to']
            values['date_from'] = post['date_from']
            values['date_to'] = post['date_to']

        if post['date_from'] > post['date_to']:
            values['error'] = _("The start date must be anterior to the end date")
            return values

        def convert_filestorage_to_base64(file_storage):
            # Assuming 'file_storage' is a FileStorage object
            file_content_bytes = file_storage.read()
            file_content_base64 = base64.b64encode(file_content_bytes).decode('utf-8')
            return file_content_base64
        try:
            _logger.info(
                "Portal leave create request started: user_id=%s employee_id=%s payload=%s",
                request.env.user.id,
                values.get('employee_id'),
                safe_post,
            )
            leave_created = request.env['hr.leave'].sudo().create(values)
            _logger.info(
                "Portal leave created: leave_id=%s state=%s date_from=%s date_to=%s request_date_from=%s request_date_to=%s",
                leave_created.id,
                leave_created.state,
                leave_created.date_from,
                leave_created.date_to,
                leave_created.request_date_from,
                leave_created.request_date_to,
            )
            # Odoo 19 already computes date/duration during create/write.
            # For leaves directly created in validated state, forcing our legacy recompute method
            # writes date fields again and triggers hr_holidays state constraints.
            _logger.info(
                "Portal leave create completed without manual post-compute: leave_id=%s state=%s",
                leave_created.id,
                leave_created.state,
            )

            if post['document']:
                your_file_storage_object = post['document']
                base64_content = convert_filestorage_to_base64(your_file_storage_object)
                partner_ids = leave_created.message_partner_ids.ids
                mail = request.env['mail.mail'].sudo().create({
                    'subject': 'Document',
                    'body_html': 'Attached a document',
                    'email_from': leave_created.create_uid.email_formatted,
                    'recipient_ids': [(6, 0, partner_ids)],
                    'attachment_ids': [(0, 0, {
                        'name': ("%s - Attached Document" % values['name']),
                        'res_model': 'hr.leave',
                        'res_id': leave_created.id,
                        'type': 'binary',
                        'datas': base64_content,
                    })] or None,
                })
                mail.send()
            values['error'] = False
            values['leave'] = leave_created
            values['user'] = request.env.user
            values['success'] = _("Submitted!")

            return values

        except Exception as error:
            request.env.cr.rollback()
            _logger.exception(
                "Portal leave create request failed: user_id=%s payload=%s values=%s error=%s",
                request.env.user.id,
                safe_post,
                values,
                error,
            )
            values['error'] = error
            return values

    @http.route(['/my/leaves/<int:leave_id>'], type='http', auth="public", website=True)
    def portal_my_leave_detail(self, leave_id, access_token=None, **kw):
        leave = request.env['hr.leave'].sudo().browse(leave_id)
        values = self._leave_get_page_view_values(leave, access_token, **kw)
        return request.render("portal_leaves.portal_leave_page", values)

    @http.route(['/my/requests/<int:leave_id>'], type='http', auth="public", website=True)
    def portal_my_request_detail(self, leave_id, access_token=None, **kw):
        leave = request.env['hr.leave'].sudo().browse(leave_id)
        values = self._request_get_page_view_values(leave, access_token, **kw)
        return request.render("portal_leaves.portal_request_page", values)

    def _leave_get_page_view_values(self, leave, access_token, **kwargs):
        values = {
            'page_name': 'leave',
            'leave': leave,
            'user': request.env.user,
        }
        return self._get_page_view_values(leave, access_token, values, 'my_leaves_history', False, **kwargs)

    def _request_get_page_view_values(self, leave, access_token, **kwargs):
        values = {
            'page_name': 'leave_requests',
            'leave': leave,
            'user': request.env.user,
        }
        if kwargs.get('document'):
            del kwargs['document']
        return self._get_page_view_values(leave.with_context(is_manager=True), access_token, values,
                                          'my_requests_history', False, **kwargs)

    @http.route(['/my/requests/refuse/<int:leave_id>'], type='http', auth="user", website=True)
    def refuse_request_leave(self, leave_id=False, access_token=None, **kw):
        leave = request.env['hr.leave'].sudo().browse(leave_id)
        leave.action_refuse()
        values = self._request_get_page_view_values(leave, access_token, **kw)
        return request.render("portal_leaves.portal_request_page", values)

    @http.route(['/my/requests/approve/<int:leave_id>'], type='http', auth="user", website=True)
    def approve_request_leave(self, leave_id=False, access_token=None, **kw):
        leave = request.env['hr.leave'].sudo().browse(leave_id)
        if leave.state == 'validate1':
            leave.sudo().action_validate()
        else:
            leave.action_approve()
        url = leave.get_portal_url_manager()
        return request.redirect(url)
