# -*- coding: utf-8 -*-
import datetime
import logging
from collections import defaultdict

import pytz

from odoo import fields, models, _, api
from odoo.exceptions import UserError, ValidationError
from datetime import datetime, timedelta, time

_logger = logging.getLogger(__name__)
try:
    from zk import ZK, const
except ImportError:
    ZK = None
    const = None
    _logger.error("Please Install pyzk library.")


class BiometricDeviceDetails(models.Model):
    """Model for configuring and connect the biometric device with odoo"""
    _name = 'biometric.device.details'
    _description = 'Biometric Device Details'

    name = fields.Char(string='Name', required=True, help='Record Name')
    device_ip = fields.Char(string='Device IP', required=True,
                            help='The IP address of the Device')
    port_number = fields.Integer(string='Port Number 1', required=True,
                                 help="The Port Number of the Device")
    port_number2 = fields.Integer(string='Port Number 2', required=True,
                                  help="The Port Number of the Device")
    port_number3 = fields.Integer(string='Port Number 3', required=True,
                                  help="The Port Number of the Device")
    company_id = fields.Many2one('res.company', string='Company',
                                 default=lambda
                                     self: self.env.user.company_id.id,
                                 help='Current Company')
    date_to = fields.Date(string="Date Range", default=fields.Date.today)
    date_from = fields.Date(string="Date from", default=fields.Date.today)

    def _ensure_pyzk_installed(self):
        """Raise a user-facing error when the external library is missing."""
        if ZK is None:
            raise UserError(
                _("The Python library 'pyzk' is not installed. Install it first with 'pip3 install pyzk'.")
            )

    def _get_configured_ports(self):
        """Return only configured TCP ports."""
        return [port for port in [self.port_number, self.port_number2, self.port_number3] if port and port > 0]

    def device_connect(self, zk):
        """Function for connecting the device with Odoo"""
        try:
            conn = zk.connect()
            return conn
        except Exception:
            return False

    @api.model
    def cron_download_attendance(self):
        """cron_download method: Perform a cron job to download attendance data for all machines.

          This method iterates through all the machines in the 'zk.machine' model and
          triggers the download_attendance method for each machine."""
        _logger.info("++++++++++++Cron Executed++++++++++++++++++++++")
        machines = self.env['biometric.device.details'].search([])
        for machine in machines:
            machine.action_download_attendance()

    def action_test_connection(self):
        """Checking the connection status"""
        self._ensure_pyzk_installed()
        success_ports = []
        error_ports = []
        ports = self._get_configured_ports()

        if not ports:
            raise ValidationError(_("Please configure at least one valid TCP port."))

        for port in ports:
            zk_client = ZK(self.device_ip, port=port, timeout=30,
                           password=False, ommit_ping=False)
            try:
                conn = zk_client.connect()
                if conn:
                    success_ports.append(port)
                    conn.disconnect()
                else:
                    error_ports.append(port)
            except Exception:
                error_ports.append(port)

        message = ""
        if success_ports:
            message += f'Successfully connected to ports: {success_ports}. '
        if error_ports:
            message += f'Failed to connect to ports: {error_ports}.'

        if success_ports:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': message,
                    'type': 'success',
                    'sticky': False
                }
            }
        else:
            raise ValidationError(message)

    def action_download_attendance(self):
        """Function to download attendance records from the device"""
        self._ensure_pyzk_installed()

        zk_attendance = self.env['zk.machine.attendance']
        hr_attendance = self.env['hr.attendance']
        for info in self:
            machine_ip = info.device_ip
            ports = info._get_configured_ports()
            if not ports:
                raise UserError(_("Please configure at least one valid TCP port."))

            connections = []
            attendance_batches = []
            for port in ports:
                zk_client = ZK(machine_ip, port=port, timeout=30,
                               password=0, force_udp=False, ommit_ping=False)
                conn = self.device_connect(zk_client)
                if conn:
                    connections.append(conn)

            if not connections:
                raise UserError(_('Unable to connect, please check the parameters and network connections.'))

            try:
                for conn in connections:
                    conn.disable_device()
                    attendance = conn.get_attendance()
                    if attendance:
                        attendance_batches.append(attendance)

                if not attendance_batches:
                    continue

                attendance_dict = defaultdict(list)
                for attendance in attendance_batches:
                    for each in attendance:
                        atten_time = each.timestamp
                        local_tz = pytz.timezone(self.env.user.partner_id.tz or 'GMT')
                        local_dt = local_tz.localize(atten_time, is_dst=None)
                        utc_dt = local_dt.astimezone(pytz.utc)
                        attendance_time = utc_dt.strftime("%Y-%m-%d %H:%M:%S")
                        atten_time_datetime = datetime.strptime(attendance_time, "%Y-%m-%d %H:%M:%S")
                        atten_date = atten_time_datetime.date()
                        if info.date_to <= atten_date <= info.date_from:
                            attendance_dict[each.user_id].append(atten_time_datetime)

                for user_id, atten_times in attendance_dict.items():
                    dates = {}
                    for atten_time in atten_times:
                        atten_date = atten_time.date()
                        if atten_date not in dates:
                            dates[atten_date] = []
                        dates[atten_date].append(atten_time)

                    for atten_date, times in dates.items():
                        times.sort()
                        if len(times) > 2:
                            times = [times[0], times[-1]]
                            dates[atten_date] = times
                        if len(times) == 1 and atten_date != datetime.now().date():
                            employee = self.env['hr.employee'].search([('device_id_num', '=', user_id)])
                            if employee and employee.shift_id and employee.shift_id.shift_out:
                                shift_out = employee.shift_id.shift_out
                                shift_out_time = time(int(shift_out - 5), int(((shift_out + 5) % 1) * 60))
                                checkout_datetime = datetime.combine(atten_date, shift_out_time)
                                times.append(checkout_datetime)
                                times.sort()
                                dates[atten_date] = times

                    updated_atten_times = [time for times in dates.values() for time in times]
                    updated_atten_times.sort()
                    attendance_dict[user_id] = updated_atten_times

                    employee = self.env['hr.employee'].search([('device_id_num', '=', user_id)])
                    if len(employee) == 1:
                        for atten_time in updated_atten_times:
                            existing_attendance = zk_attendance.search(
                                [('device_id_num', '=', user_id), ('check_out', '=', False)], limit=1)
                            existing_hr_attendance = hr_attendance.search(
                                [('employee_id', '=', employee.id), ('check_out', '=', False)], limit=1)
                            if existing_attendance:
                                for exist in existing_attendance:
                                    if not exist.check_in == atten_time:
                                        if exist.check_in.date() == atten_time.date():
                                            if exist.check_in > atten_time:
                                                exist.write({
                                                    'check_in': atten_time,
                                                    'check_out': exist.check_in,
                                                    'o_check': 'o',
                                                })
                                            else:
                                                if exist.check_out:
                                                    if not exist.check_out > atten_time:
                                                        exist.write({
                                                            'check_out': atten_time,
                                                            'o_check': 'o',
                                                        })
                                                        if existing_hr_attendance:
                                                            existing_hr_attendance.write({
                                                                'employee_id': employee.id,
                                                                'check_out': atten_time
                                                            })
                                                else:
                                                    exist.write({
                                                        'check_out': atten_time,
                                                        'o_check': 'o',
                                                    })
                                                    if existing_hr_attendance:
                                                        existing_hr_attendance.write({
                                                            'employee_id': employee.id,
                                                            'check_out': atten_time
                                                        })
                                        else:
                                            if not exist.check_in == atten_time:
                                                check_in_atten = zk_attendance.search(
                                                    [('check_in', '=', atten_time), ('device_id_num', '=', user_id)])
                                                check_out_atten = zk_attendance.search(
                                                    [('check_out', '=', atten_time), ('device_id_num', '=', user_id)])
                                                if not check_in_atten and not check_out_atten:
                                                    zk_attendance.create({
                                                        'employee_id': employee.id,
                                                        'check_in': atten_time,
                                                        'check_out': False,
                                                        'i_check': 'i',
                                                        'device_id_num': user_id
                                                    })
                                                    hr_attendance.create({
                                                        'employee_id': employee.id,
                                                        'check_in': atten_time
                                                    })
                            else:
                                check_in_atten = zk_attendance.search(
                                    [('check_in', '=', atten_time), ('device_id_num', '=', user_id)])
                                check_out_atten = zk_attendance.search(
                                    [('check_out', '=', atten_time), ('device_id_num', '=', user_id)])
                                if not check_in_atten and not check_out_atten:
                                    zk_attendance.create({
                                        'employee_id': employee.id,
                                        'check_in': atten_time,
                                        'check_out': False,
                                        'device_id_num': user_id,
                                        'i_check': 'i',
                                    })
                                    hr_attendance.create({
                                        'employee_id': employee.id,
                                        'check_in': atten_time
                                    })
                    elif len(employee) > 1:
                        raise ValidationError(
                            "More Than One Employee Is Found With The Same Device Id" + user_id)
            finally:
                for conn in connections:
                    try:
                        conn.disconnect()
                    except Exception:
                        _logger.exception("Failed to disconnect from biometric device.")

        return True

    def action_restart_device(self):
        """For restarting the device"""
        self._ensure_pyzk_installed()
        try:
            ports = self._get_configured_ports()
            if not ports:
                raise ValidationError(_("Please configure at least one valid TCP port."))

            for port in ports:
                zk_client = ZK(self.device_ip, port=port, timeout=30,
                               password=0, force_udp=False, ommit_ping=False)
                conn = self.device_connect(zk_client)
                if conn:
                    conn.restart()
                    conn.disconnect()
        except Exception as error:
            raise ValidationError(f'{error}')
