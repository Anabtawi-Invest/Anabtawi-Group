/** @odoo-module **/

import publicWidget from '@web/legacy/js/public/public_widget';
import { rpc } from "@web/core/network/rpc";

publicWidget.registry.LeaveCreation = publicWidget.Widget.extend({
    selector: 'form.leaves_form',
    events: {
        'change select[name=holiday_status_id]': "_onTypeChange",
        'input input[name=request_unit_hours]': "_onHoursClick",
        'input input[name=request_unit_half]': '_onHalfClick',
        'change input[type=date], select[name=request_date_from_period]': '_onDateTimeChange',
        'change select[name=request_hour_from], select[name=request_hour_to]': '_onDateTimeChange',
    },


    _getLeaveType: function () {
        this.$typeInput = this.$('select[name="holiday_status_id"]');
        this.$type = this.$typeInput.val();
        this.$unitType = this.$typeInput.find("option[value=" + this.$type + "]").attr("request-unit");
    },

    _adaptLeaveType: function () {
        this._getLeaveType();
        $("select[name=request_date_from_period]").hide();
        $(".unit_half, .unit_hours").show();

        rpc('/web/dataset/call_kw/hr.leave.type/get_support_document_bool_js', {
            model: 'hr.leave.type',
            method: 'get_support_document_bool_js',
            args: [parseInt(this.$type)],
            kwargs: {},
        }).then(function (result) {
            if (result === true) {
                $(".document").show();
            } else {
                $(".document").hide();
            }
        });

        if (this.$unitType == 'day') {
            $(".request_unit_checkboxes, .hours").removeClass("d-flex");
            $(".request_unit_checkboxes, .hours").hide();
            $(".hours").hide();
            $(".to, input[name=date_to]").show();

        }
        $(".hours").removeClass("d-flex");
        $(".hours").hide();

        if (this.$unitType == 'hour') {
            $(".request_unit_checkboxes").addClass("d-flex");
            $(".request_unit_checkboxes").show();
            // For hour-based leave types, enforce hours mode directly.
            $(".unit_half, .unit_hours").hide();
            $("input[name=request_unit_half]").prop("checked", false).val(false);
            $("input[name=request_unit_hours]").prop("checked", true).val(true);
            $("input[name=request_unit]").val("hours");
            $(".hours").addClass("d-flex");
            $(".hours, .hours .to").show();
            $(".to, input[name=date_to]").hide();
        }

        if (this.$unitType == 'half_day') {
            $(".request_unit_checkboxes").addClass("d-flex");
            $(".request_unit_checkboxes").show();
            $(".unit_hours").hide();
            $(".hours").hide();
            if ($("input[name=request_unit_half]").is(":checked")) {
                $("select[name=request_date_from_period]").show();
            }
        }

        if (!$("input[name=request_unit_hours]").is(":checked") && $("input[name=request_unit_half]").is(":checked")) {
            $("#edit_leave_request .unit_hours").hide();
        }

        if ($("input[name=request_unit_hours]").is(":checked") && !$("input[name=request_unit_half]").is(":checked")) {
            $("#edit_leave_request .unit_half").hide();
        }

        if (!$("input[name=request_unit_hours]").is(":checked") && !$("input[name=request_unit_half]").is(":checked")) {
            $("#edit_leave_request .request_unit_checkboxes").hide();
            $("#edit_leave_request .request_unit_checkboxes").removeClass("d-flex");
        }
    },

    _getHoursFromTo: function () {
        var hour_from_input = $("[name=request_hour_from]");
        var hour_to_input = $("[name=request_hour_to]");
        var hour_from = hour_from_input.val();
        var hour_to = hour_to_input.val();
        return {hour_from, hour_to};
    },

    _initTimeOptions: function () {
        const $from = this.$("select[name=request_hour_from]");
        const $to = this.$("select[name=request_hour_to]");
        if (!$from.length || !$to.length) return;
        if ($from.find("option").length > 1 && $to.find("option").length > 1) return;

        const currentFrom = $from.val();
        const currentTo = $to.val();
        for (let hour = 0; hour < 24; hour++) {
            for (let minute = 0; minute < 60; minute += 30) {
                const hh = String(hour).padStart(2, "0");
                const mm = String(minute).padStart(2, "0");
                const value = `${hh}:${mm}`;
                const displayHour24 = hour;
                const ampm = displayHour24 >= 12 ? "PM" : "AM";
                const displayHour12 = displayHour24 % 12 === 0 ? 12 : displayHour24 % 12;
                const label = `${displayHour12}:${mm} ${ampm}`;
                $from.append($("<option/>", { value, text: label }));
                $to.append($("<option/>", { value, text: label }));
            }
        }
        if (currentFrom) $from.val(currentFrom);
        if (currentTo) $to.val(currentTo);
    },

    _calculateDuration: function (type) {
        this.$status = $("select[name=holiday_status_id]").val();
        var date_from_input = $("input[name=date_from]");
        var date_to_input = $("input[name=date_to]");
        var date_from = date_from_input.val();
        var date_to = date_to_input.val();
        var durationInput = $("input[name=number_of_days]");

        if (new Date(date_to).getDate() < new Date(date_from).getDate()) {
            let string = 'days';
            if ($("#wrapwrap").hasClass("o_rtl")) string = "يوم";
            durationInput.val(0 + " " + string);
        }
        var half_day = $("input[name=request_unit_half]").is(":checked");
        var hours = $("input[name=request_unit_hours]").is(":checked");
        if (!half_day && !hours) {
            var days = 0;
            $("input[name=request_unit]").val("");

            rpc('/web/dataset/call_kw/hr.leave/get_number_of_days_ajax', {
                model: 'hr.leave',
                method: 'get_number_of_days_ajax',
                args: ['', date_from, date_to, false, false, false, false, true, false, parseInt(this.$employee), parseInt(this.$status)],
                kwargs: {},
            }).then(function (duration) {
                if (type == 'day' || type == 'half_day') {
                    if (duration['days'] >= 0) {
                        let string = 'days';
                        if ($("#wrapwrap").hasClass("o_rtl")) string = "يوم";
                        durationInput.val(duration['days'] + " " + string);
                    }
                } else {
                    if (duration['hours']) days = duration['hours'];
                    let string = 'hours';
                    if ($("#wrapwrap").hasClass("o_rtl")) string = "ساعة";
                    durationInput.val(days + " " + string);
                }
            });
        } else {
            if (half_day && date_from) {
                days = 0;
                date_to_input.val(date_from_input.val());
                date_to = date_from;
                var request_date_from_period = $("select[name='request_date_from_period']").val();
                $("input[name=request_unit]").val("half_day");

                rpc('/web/dataset/call_kw/hr.leave/get_number_of_days_ajax', {
                    model: 'hr.leave',
                    method: 'get_number_of_days_ajax',
                    args: ['', date_from, date_to, false, false, true, false, false, request_date_from_period, parseInt(this.$employee), parseInt(this.$status)],
                    kwargs: {},
                }).then(function (duration) {
                    if (type == 'day' || type == 'half_day') {
                        if (duration['days'] >= 0) {
                            let string = 'days';
                            if ($("#wrapwrap").hasClass("o_rtl")) string = "يوم";
                            durationInput.val(duration['days'] + " " + string);
                        }
                    } else {
                        if (duration['hours'] > 0) days = duration['hours'];
                        let string = 'hours';
                        if ($("#wrapwrap").hasClass("o_rtl")) string = "ساعة";
                        durationInput.val(days + " " + string);
                    }
                });
            }
            if (hours && date_from) {
                date_to_input.val(date_from_input.val());
                date_to = date_from;
                var hour_from, hour_to = false;
                var hour_from_to = this._getHoursFromTo();
                hour_from = hour_from_to['hour_from'];
                hour_to = hour_from_to['hour_to'];
                if (hour_to && hour_from) {
                    var convertTimeToFloat = function (timeStr) {
                        var parts = timeStr.split(':');
                        var hours = parseFloat(parts[0]);
                        var minutes = parseFloat(parts[1]) / 60;
                        return hours + minutes;
                    };

                    var float_hour_from = convertTimeToFloat(hour_from);
                    var float_hour_to = convertTimeToFloat(hour_to);

                    $("input[name=request_unit]").val("hours");

                    rpc('/web/dataset/call_kw/hr.leave/get_number_of_days_ajax', {
                        model: 'hr.leave',
                        method: 'get_number_of_days_ajax',
                        args: ['', date_from, date_to, float_hour_from, float_hour_to, false, true, false, false, parseInt(this.$employee), parseInt(this.$status)],
                        kwargs: {},
                    }).then(function (duration) {
                        let string = 'hours';
                        if ($("#wrapwrap").hasClass("o_rtl")) string = "ساعة";
                        durationInput.val(duration['hours'] + ' ' + string);
                    });
                }
            }
        }
    },

    start: function () {
        var def = this._super.apply(this, arguments);
        this._initTimeOptions();
        this._adaptLeaveType();
        this.$employee = $("input[name=employee_id]").val();
        $("input[name=request_unit]").val("");
        if ($("input[name='request_unit_hours']").is(":checked")) {
            $("input[name=request_unit]").val("hours");
            $('.hours').addClass('d-flex');
            $(".to, input[name=date_to]").hide();
            $('.hours, .hours .to').show();
            $("input[name=request_unit_half]").val(false)
        }

        if ($("input[name=request_unit_half]").is(":checked")) {
            $("input[name=request_unit]").val("half_day");
            $('.hours').removeClass('d-flex');
            $('.hours').hide();
            $(".to, input[name=date_to]").hide();
            $("select[name=request_date_from_period]").show();
            $("input[name=request_unit_hours]").val(false)
        }

        return def;
    },

    _onHoursClick: function (ev) {
        var isChecked = $(ev.currentTarget).is(":checked");
        $("select[name=request_date_from_period]").hide();
        $("input[name=number_of_days]").val("");
        if (isChecked) {
            $("input[name=request_unit]").val("hours");
            $('.hours').addClass('d-flex');
            $(".to, input[name=date_to]").hide();
            $('.hours, .hours .to').show();
            $(ev.currentTarget).val(true);
            $("input[name=request_unit_half]").prop("checked", false);
            $("input[name=request_unit_half]").val(false)
        } else {
            $("input[name=request_unit]").val("");
            $(ev.currentTarget).val(false);
            $('.hours').removeClass('d-flex');
            $('.hours').hide();
            $(".to, input[name=date_to]").show();
        }
        this._getLeaveType();
        this._calculateDuration(this.$unitType);
    },

    _onHalfClick: function (ev) {
        var isChecked = $(ev.currentTarget).is(":checked");
        if (isChecked) {
            $("input[name=request_unit]").val("half_day");
            $('.hours').removeClass('d-flex');
            $('.hours').hide();
            $(".to, input[name=date_to]").hide();
            $("input[name=request_unit_hours]").prop("checked", false);
            $("select[name=request_date_from_period]").show();
            $(ev.currentTarget).val(true);
            $("input[name=request_unit_hours]").val(false);
        } else {
            $("input[name=request_unit]").val("");
            $("select[name=request_date_from_period]").hide();
            $('.hours').removeClass('d-flex');
            $('.hours').hide();
            $(".to, input[name=date_to]").show();
            $(ev.currentTarget).val(false);
        }
        this._getLeaveType();
        this._calculateDuration(this.$unitType);
    },

    _onTypeChange: function (ev) {
        $("input[name=number_of_days]").val("");
        $("input[name=request_unit]").val(false);
        $("input[name=request_unit_half]").prop("checked", false);
        $("input[name=request_unit_half]").val(false);
        $("input[name=request_unit_hours]").prop("checked", false);
        $("input[name=request_unit_hours]").val(false);
        $("select[name='request_hour_from']").val("");
        $("select[name='request_hour_to']").val("");
        this._adaptLeaveType();
    },

    _onDateTimeChange: function (ev) {
        this._getLeaveType();
        this._calculateDuration(this.$unitType);
    }
});
