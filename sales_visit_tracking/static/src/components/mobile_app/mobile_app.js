/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, onWillUnmount, useState } from "@odoo/owl";

export class SalesVisitMobileApp extends Component {
    static template = "sales_visit_tracking.SalesVisitMobileApp";

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.action = useService("action");

        this.state = useState({
            view: 'home', // 'home', 'visiting', 'result'
            visits: [],
            activeVisit: null,
            timeElapsed: "00:00",
            selectedOutcome: "", // 'revisit', 'rejected', 'order', 'issue'
            revisitDate: new Date(Date.now() + 86400000).toISOString().split('T')[0], // tomorrow
            rejectionReason: "not_interested",
            customerIssue: "",
            gps: { lat: 0.0, lon: 0.0 },
            loading: false
        });

        onWillStart(async () => {
            await this.loadVisits();
        });

        onWillUnmount(() => {
            this.clearTimer();
        });
    }

    async loadVisits() {
        this.state.loading = true;
        try {
            const data = await this.orm.call('sales.visit', 'get_my_visits_for_mobile', []);
            this.state.visits = data;

            // Check if there is an in-progress visit to recover
            const active = data.find(v => v.state === 'in_progress');
            if (active) {
                this.state.activeVisit = active;
                this.state.view = 'visiting';
                this.startTimer();
            }
        } catch (error) {
            console.error("Failed to load visits", error);
            this.notification.add("Could not fetch visits list.", { type: "danger" });
        } finally {
            this.state.loading = false;
        }
    }

    onNavigate(visit) {
        if (!visit.lat || !visit.lon) {
            this.notification.add("Location coordinates are not set yet.", { type: "warning" });
            return;
        }
        const url = `https://www.google.com/maps/dir/?api=1&destination=${visit.lat},${visit.lon}`;
        window.open(url, '_blank');
    }

    async getCoordinates() {
        return new Promise((resolve, reject) => {
            if (!navigator.geolocation) {
                reject(new Error("Geolocation is not supported by your device."));
                return;
            }
            navigator.geolocation.getCurrentPosition(
                (pos) => resolve({ lat: pos.coords.latitude, lon: pos.coords.longitude }),
                (err) => reject(err),
                { enableHighAccuracy: true, timeout: 8000 }
            );
        });
    }

    async onSaveLocationAndCheckIn(visit) {
        this.state.loading = true;
        try {
            const coords = await this.getCoordinates();
            this.state.gps = coords;

            await this.orm.call(
                'sales.visit',
                'action_save_lead_location_and_check_in',
                [visit.id],
                {
                    latitude: coords.lat,
                    longitude: coords.lon
                }
            );

            this.state.activeVisit = visit;
            this.state.view = 'visiting';
            this.startTimer();
            this.notification.add("Location saved & Checked-In successfully.", { type: "success" });
        } catch (error) {
            console.error("Failed to save location & check-in", error);
            // Error is handled/shown by Odoo's default RPC handlers, but alert user as fallback
            this.notification.add("Could not capture GPS location. Check device settings.", { type: "danger" });
        } finally {
            this.state.loading = false;
        }
    }

    async onCheckIn(visit) {
        this.state.loading = true;
        try {
            const coords = await this.getCoordinates();
            this.state.gps = coords;

            await this.orm.call(
                'sales.visit',
                'action_check_in',
                [visit.id],
                {
                    latitude: coords.lat,
                    longitude: coords.lon
                }
            );

            this.state.activeVisit = visit;
            this.state.view = 'visiting';
            this.startTimer();
            this.notification.add("Checked in successfully.", { type: "success" });
        } catch (error) {
            console.error("Check-in failed", error);
            // Blocked by geofencing or permission error
            this.notification.add(error.data?.message || "Check-in blocked. Make sure GPS is enabled and you are within 50m of the customer.", { type: "danger", sticky: true });
        } finally {
            this.state.loading = false;
        }
    }

    async onEndVisit() {
        this.state.loading = true;
        try {
            const coords = await this.getCoordinates();
            this.state.gps = coords;
            this.clearTimer();
            this.state.view = 'result';
        } catch (error) {
            console.error("Failed to end visit", error);
            this.notification.add("Failed to capture checkout GPS. Check location permissions.", { type: "danger" });
        } finally {
            this.state.loading = false;
        }
    }

    async selectOutcome(outcome) {
        if (outcome === 'approved') {
            this.state.loading = true;
            try {
                await this.orm.call(
                    'sales.visit',
                    'action_end_visit',
                    [this.state.activeVisit.id],
                    {
                        latitude: this.state.gps.lat,
                        longitude: this.state.gps.lon,
                        result: 'approved'
                    }
                );
                this.notification.add("Lead approved & converted successfully!", { type: "success" });
                await this.resetToHome();
            } catch (error) {
                console.error("Failed to approve lead", error);
            } finally {
                this.state.loading = false;
            }
        } else {
            this.state.selectedOutcome = outcome;
        }
    }

    async createSalesOrderAction(orderType) {
        this.state.loading = true;
        try {
            // First end the visit on the server with outcome 'order'
            await this.orm.call(
                'sales.visit',
                'action_end_visit',
                [this.state.activeVisit.id],
                {
                    latitude: this.state.gps.lat,
                    longitude: this.state.gps.lon,
                    result: 'order'
                }
            );

            this.notification.add("Visit completed with Order. Opening form...", { type: "success" });

            // Launch standard Odoo action to create sales order/quotation
            this.action.doAction({
                type: 'ir.actions.act_window',
                name: orderType === 'quotation' ? 'New Quotation' : 'New Sales Order',
                res_model: 'sale.order',
                views: [[false, 'form']],
                target: 'current',
                context: {
                    'default_partner_id': this.state.activeVisit.partner_id || false,
                    'default_visit_id': this.state.activeVisit.id,
                    'default_pricelist_id': false, // lets Odoo compute default pricelist
                }
            });

            await this.resetToHome();
        } catch (error) {
            console.error("Failed to create order action", error);
        } finally {
            this.state.loading = false;
        }
    }

    async onSubmitDetails() {
        this.state.loading = true;
        try {
            const vals = {
                latitude: this.state.gps.lat,
                longitude: this.state.gps.lon,
                result: this.state.selectedOutcome
            };

            if (this.state.selectedOutcome === 'revisit') {
                vals.next_visit_date = this.state.revisitDate;
            } else if (this.state.selectedOutcome === 'rejected') {
                vals.rejection_reason = this.state.rejectionReason;
            } else if (this.state.selectedOutcome === 'issue') {
                vals.customer_issue = this.state.customerIssue;
            }

            await this.orm.call(
                'sales.visit',
                'action_end_visit',
                [this.state.activeVisit.id],
                vals
            );

            this.notification.add("Outcome saved successfully.", { type: "success" });
            await this.resetToHome();
        } catch (error) {
            console.error("Failed to save outcome details", error);
        } finally {
            this.state.loading = false;
        }
    }

    onCancelDetails() {
        this.state.selectedOutcome = "";
    }

    async resetToHome() {
        this.state.view = 'home';
        this.state.activeVisit = null;
        this.state.selectedOutcome = "";
        this.state.customerIssue = "";
        await this.loadVisits();
    }

    startTimer() {
        this.startTime = Date.now();
        this.timer = setInterval(() => {
            const diffMs = Date.now() - this.startTime;
            const diffSecs = Math.floor(diffMs / 1000);
            const mins = Math.floor(diffSecs / 60).toString().padStart(2, '0');
            const secs = (diffSecs % 60).toString().padStart(2, '0');
            this.state.timeElapsed = `${mins}:${secs}`;
        }, 1000);
    }

    clearTimer() {
        if (this.timer) {
            clearInterval(this.timer);
            this.timer = null;
        }
        this.state.timeElapsed = "00:00";
    }

    onRefresh() {
        this.loadVisits();
    }
}

registry.category("actions").add("sales_visit_mobile_app", SalesVisitMobileApp);
