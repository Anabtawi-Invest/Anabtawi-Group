/** @odoo-module **/

import { whenReady } from "@odoo/owl";

function setupPortalDashboardNavigation() {
    const wrapper = document.querySelector(".o_portal_dashboard_wrapper");
    if (!wrapper) {
        return;
    }

    const iframe = wrapper.querySelector("#o_portal_dashboard_iframe");
    const title = wrapper.querySelector("#o_portal_dashboard_title");
    const navItems = wrapper.querySelectorAll(".o_portal_dashboard_nav_item");
    if (!iframe || !title || !navItems.length) {
        return;
    }

    const setActive = (clickedItem) => {
        navItems.forEach((item) => item.classList.toggle("is-active", item === clickedItem));
    };

    navItems.forEach((item) => {
        item.addEventListener("click", (event) => {
            const url = item.dataset.contentUrl;
            if (!url) {
                return;
            }
            // Preserve current behavior by loading existing feature pages directly,
            // while avoiding full dashboard reloads for sidebar navigation.
            event.preventDefault();
            iframe.src = url;
            title.textContent = item.textContent.trim();
            setActive(item);
            window.history.replaceState({}, "", item.href);

            const offcanvas = wrapper.querySelector("#o_portal_dashboard_sidebar");
            if (offcanvas && offcanvas.classList.contains("show")) {
                const closeBtn = offcanvas.querySelector(".btn-close");
                if (closeBtn) {
                    closeBtn.click();
                }
            }
        });
    });
}

whenReady(setupPortalDashboardNavigation);
