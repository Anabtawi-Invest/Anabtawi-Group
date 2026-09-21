/** @odoo-module **/

import { whenReady } from "@odoo/owl";
import { rpc } from "@web/core/network/rpc";

function qs(sel, root = document) {
    return root.querySelector(sel);
}

whenReady().then(start);
document.addEventListener("DOMContentLoaded", start);
if (document.readyState !== "loading") {
    start();
}

function start() {
    if (window.__portalCustomerRequestInit) {
        return;
    }
    window.__portalCustomerRequestInit = true;
    const createRoot = qs(".o_portal_customer_request_create");
    if (createRoot) {
        initCreatePage(createRoot);
    }
    const detailRoot = qs(".o_portal_customer_request_detail");
    if (detailRoot) {
        initDetailPage(detailRoot);
    }
}

function errorMessage(err) {
    return (
        (err && (err.data && err.data.message)) ||
        (err && err.message) ||
        (typeof err === "string" ? err : "") ||
        "Unexpected error"
    );
}

async function submitRequest(payload) {
    try {
        return await rpc("/my/customer-requests/api/submit", payload);
    } catch (e1) {
        const response = await fetch("/my/customer-requests/api/submit/http", {
            method: "POST",
            credentials: "same-origin",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        });
        if (!response.ok) {
            throw e1;
        }
        return await response.json();
    }
}

async function cancelRequest(requestId) {
    try {
        return await rpc("/my/customer-requests/api/cancel", { request_id: requestId });
    } catch (e1) {
        const response = await fetch("/my/customer-requests/api/cancel/http", {
            method: "POST",
            credentials: "same-origin",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ request_id: requestId }),
        });
        if (!response.ok) {
            throw e1;
        }
        return await response.json();
    }
}

function initCreatePage(root) {
    const nameInput = qs("#customer_name", root);
    const phoneInput = qs("#customer_phone", root);
    const emailInput = qs("#customer_email", root);
    const submitBtn = qs("#btn_submit_customer_request", root);
    const errorEl = qs("#submit_error", root);

    if (!submitBtn) {
        return;
    }

    submitBtn.addEventListener("click", async () => {
        if (errorEl) {
            errorEl.classList.add("d-none");
            errorEl.textContent = "";
        }
        const name = (nameInput && nameInput.value) || "";
        const phone = (phoneInput && phoneInput.value) || "";
        const email = (emailInput && emailInput.value) || "";
        if (!name.trim()) {
            if (errorEl) {
                errorEl.textContent = "Customer name is required.";
                errorEl.classList.remove("d-none");
            }
            return;
        }
        submitBtn.disabled = true;
        try {
            const result = await submitRequest({ name, phone, email });
            window.location.href = result.redirect_url || "/my/customer-requests";
        } catch (err) {
            if (errorEl) {
                errorEl.textContent = errorMessage(err);
                errorEl.classList.remove("d-none");
            }
            submitBtn.disabled = false;
        }
    });
}

function initDetailPage(root) {
    const cancelBtn = qs("#btn_cancel_customer_request", root);
    const errorEl = qs("#cancel_error", root);
    if (!cancelBtn) {
        return;
    }
    const requestId = parseInt(root.dataset.requestId, 10);
    cancelBtn.addEventListener("click", async () => {
        if (!window.confirm("Cancel this customer request?")) {
            return;
        }
        if (errorEl) {
            errorEl.classList.add("d-none");
            errorEl.textContent = "";
        }
        cancelBtn.disabled = true;
        try {
            await cancelRequest(requestId);
            window.location.reload();
        } catch (err) {
            if (errorEl) {
                errorEl.textContent = errorMessage(err);
                errorEl.classList.remove("d-none");
            }
            cancelBtn.disabled = false;
        }
    });
}
