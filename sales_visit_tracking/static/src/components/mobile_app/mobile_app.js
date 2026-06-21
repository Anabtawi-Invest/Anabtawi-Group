/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { user } from "@web/core/user";
import { Component, onWillStart, onWillUnmount, useState } from "@odoo/owl";

export class SalesVisitMobileApp extends Component {
    static template = "sales_visit_tracking.SalesVisitMobileApp";

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");

        this.state = useState({
            view: 'home', // 'home', 'visiting', 'result'
            leads: [],
            activeLead: null,
            activeVisitId: null,
            timeElapsed: "00:00",
            selectedOutcome: "", // 'revisit', 'rejected'
            revisitDate: new Date(Date.now() + 86400000).toISOString().split('T')[0], // tomorrow
            rejectionReason: "not_interested",
            gps: { lat: 0.0, lon: 0.0 },
            loading: false
        });

        onWillStart(async () => {
            await this.loadLeads();
        });

        onWillUnmount(() => {
            this.clearTimer();
        });
    }

    async loadLeads() {
        this.state.loading = true;
        try {
            const domain = [
                ['status', 'in', ['lead', 'revisit']],
                ['user_id', '=', user.userId]
            ];
            this.state.leads = await this.orm.searchRead(
                'sales.visit.lead',
                domain,
                ['id', 'name', 'mobile', 'latitude', 'longitude', 'status']
            );
        } catch (error) {
            console.error("Failed to load leads", error);
            this.notification.add("Could not fetch leads list.", { type: "danger" });
        } finally {
            this.state.loading = false;
        }
    }

    onNavigate(lead) {
        if (!lead.latitude || !lead.longitude) {
            this.notification.add("Lead does not have GPS coordinates set.", { type: "warning" });
            return;
        }
        const url = `https://www.google.com/maps/dir/?api=1&destination=${lead.latitude},${lead.longitude}`;
        window.open(url, '_blank');
    }

    async getCoordinates() {
        return new Promise((resolve, reject) => {
            if (!navigator.geolocation) {
                reject(new Error("Geolocation not supported."));
                return;
            }
            navigator.geolocation.getCurrentPosition(
                (pos) => resolve({ lat: pos.coords.latitude, lon: pos.coords.longitude }),
                (err) => reject(err),
                { enableHighAccuracy: true, timeout: 8000 }
            );
        });
    }

    async onStartVisit(lead) {
        this.state.loading = true;
        try {
            const coords = await this.getCoordinates();
            this.state.gps = coords;

            const visitId = await this.orm.call(
                'sales.visit',
                'action_start_visit',
                [],
                {
                    lead_id: lead.id,
                    latitude: coords.lat,
                    longitude: coords.lon
                }
            );

            this.state.activeVisitId = visitId;
            this.state.activeLead = lead;
            this.state.view = 'visiting';
            this.startTimer();
            this.notification.add("Visit started successfully.", { type: "success" });
        } catch (error) {
            console.error("Failed to start visit", error);
            this.notification.add("Failed to start visit. Please check GPS permission.", { type: "danger" });
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
                    [this.state.activeVisitId],
                    {
                        latitude: this.state.gps.lat,
                        longitude: this.state.gps.lon,
                        result: 'approved'
                    }
                );
                this.notification.add("Customer Approved & Converted successfully!", { type: "success" });
                await this.resetToHome();
            } catch (error) {
                console.error("Failed to approve visit", error);
            } finally {
                this.state.loading = false;
            }
        } else {
            this.state.selectedOutcome = outcome;
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
            }

            await this.orm.call(
                'sales.visit',
                'action_end_visit',
                [this.state.activeVisitId],
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
        this.state.activeLead = null;
        this.state.activeVisitId = null;
        this.state.selectedOutcome = "";
        await this.loadLeads();
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
        this.loadLeads();
    }
}

registry.category("actions").add("sales_visit_mobile_app", SalesVisitMobileApp);
