/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, onMounted, onWillUnmount, useState, useRef } from "@odoo/owl";

export class SalesRouteMap extends Component {
    static template = "sales_visit_tracking.SalesRouteMap";
    
    setup() {
        this.orm = useService("orm");
        this.mapRef = useRef("map_canvas");
        this.state = useState({
            selectedEmployee: "",
            selectedDate: new Date().toISOString().split('T')[0],
            employees: [],
            mapData: {
                customers: [],
                visits: [],
                routes: [],
                reps: []
            }
        });

        this.markers = [];
        this.routeLine = null;

        onWillStart(async () => {
            await this.loadMapData();
        });

        onMounted(() => {
            this.initMap();
            this.renderMapElements();
        });

        onWillUnmount(() => {
            if (this.map) {
                this.map.remove();
            }
        });
    }

    async loadMapData() {
        try {
            const data = await this.orm.call("sales.visit", "get_map_data", [], {
                employee_id: this.state.selectedEmployee ? parseInt(this.state.selectedEmployee) : false,
                date_str: this.state.selectedDate
            });
            this.state.mapData = data;
            this.state.employees = data.employees || [];
        } catch (error) {
            console.error("Failed to load map data", error);
        }
    }

    initMap() {
        const el = this.mapRef.el;
        if (!el || !window.L) {
            return;
        }

        // Default to Amman, Jordan (Center coordinates for HQ)
        this.map = window.L.map(el).setView([31.9522, 35.9106], 10);
        
        window.L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            maxZoom: 19,
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        }).addTo(this.map);
    }

    clearMapElements() {
        this.markers.forEach(m => this.map.removeLayer(m));
        this.markers = [];
        if (this.routeLine) {
            this.map.removeLayer(this.routeLine);
            this.routeLine = null;
        }
    }

    renderMapElements() {
        if (!this.map || !window.L) return;

        this.clearMapElements();

        const L = window.L;
        const bounds = [];

        // 1. Render Customers / Leads (Blue, Yellow, and Orange Pins)
        this.state.mapData.customers.forEach(c => {
            let color = "#3b82f6"; // Customer (Blue)
            let iconClass = "fa-building";
            if (c.status === 'LEAD') {
                color = "#eab308"; // Lead (Yellow)
                iconClass = "fa-star";
            } else if (c.status === 'REVISIT') {
                color = "#f97316"; // Revisit (Orange)
                iconClass = "fa-refresh";
            }

            const markerHtml = `<div class="custom-marker-partner" style="width: 24px; height: 24px; border-radius: 50%; background: ${color}; border: 2px solid white; box-shadow: 0 2px 4px rgba(0,0,0,0.3); display: flex; align-items: center; justify-content: center; color: white;"><i class="fa ${iconClass}" style="font-size: 10px;"></i></div>`;
            const icon = L.divIcon({
                html: markerHtml,
                className: 'custom-div-icon',
                iconSize: [24, 24],
                iconAnchor: [12, 12]
            });
            const m = L.marker([c.lat, c.lon], { icon: icon })
                .bindPopup(`<b>Name:</b> ${c.name}<br/><b>Type:</b> ${c.status}`)
                .addTo(this.map);
            this.markers.push(m);
            bounds.push([c.lat, c.lon]);
        });

        // 2. Render Check-in / Check-out locations (Green Pins)
        this.state.mapData.visits.forEach(v => {
            if (v.lat && v.lon) {
                const markerHtml = `<div class="custom-marker-checkin" style="width: 24px; height: 24px; border-radius: 50%; background: #10b981; border: 2px solid white; box-shadow: 0 2px 4px rgba(0,0,0,0.3); display: flex; align-items: center; justify-content: center; color: white;"><i class="fa fa-sign-in" style="font-size: 10px;"></i></div>`;
                const icon = L.divIcon({
                    html: markerHtml,
                    className: 'custom-div-icon',
                    iconSize: [24, 24],
                    iconAnchor: [12, 12]
                });
                const m = L.marker([v.lat, v.lon], { icon: icon })
                    .bindPopup(`<b>Check-In:</b> ${v.name}<br/><b>Salesperson:</b> ${v.salesperson}<br/><b>Status:</b> ${v.status}<br/><b>Outcome:</b> ${v.outcome}`)
                    .addTo(this.map);
                this.markers.push(m);
                bounds.push([v.lat, v.lon]);
            }
        });

        // 3. Render Route path line (Small Red Dots)
        const routeCoords = [];
        this.state.mapData.routes.forEach(r => {
            routeCoords.push([r.lat, r.lon]);
            
            const markerHtml = `<div class="custom-marker-ping" style="width: 12px; height: 12px; border-radius: 50%; background: #ef4444; border: 1.5px solid white; box-shadow: 0 1px 3px rgba(0,0,0,0.3);"></div>`;
            const icon = L.divIcon({
                html: markerHtml,
                className: 'custom-div-icon-ping',
                iconSize: [12, 12],
                iconAnchor: [6, 6]
            });
            const m = L.marker([r.lat, r.lon], { icon: icon })
                .bindPopup(`<b>Employee:</b> ${r.employee}<br/><b>Time:</b> ${r.time}<br/><b>Speed:</b> ${r.speed} km/h`)
                .addTo(this.map);
            this.markers.push(m);
            bounds.push([r.lat, r.lon]);
        });

        if (routeCoords.length > 1) {
            this.routeLine = L.polyline(routeCoords, { color: '#7c5dfa', weight: 4, opacity: 0.8 }).addTo(this.map);
        }

        // 4. Render Live Salesperson Positions (Indigo Pins)
        this.state.mapData.reps.forEach(rep => {
            const markerHtml = `<div class="custom-marker-rep-live" style="width: 28px; height: 28px; border-radius: 50%; background: #4f46e5; border: 2.5px solid white; box-shadow: 0 3px 6px rgba(0,0,0,0.4); display: flex; align-items: center; justify-content: center; color: white;"><i class="fa fa-user" style="font-size: 11px;"></i></div>`;
            const icon = L.divIcon({
                html: markerHtml,
                className: 'custom-div-icon',
                iconSize: [28, 28],
                iconAnchor: [14, 14]
            });
            const m = L.marker([rep.lat, rep.lon], { icon: icon })
                .bindPopup(`<b>Sales Representative:</b> ${rep.name}<br/><b>Last Active:</b> ${rep.time}`)
                .addTo(this.map);
            this.markers.push(m);
            bounds.push([rep.lat, rep.lon]);
        });

        if (bounds.length > 0) {
            this.map.fitBounds(bounds, { padding: [50, 50] });
        }
    }

    async onApplyFilters() {
        await this.loadMapData();
        this.renderMapElements();
    }
}

registry.category("actions").add("sales_visit_route_map", SalesRouteMap);
