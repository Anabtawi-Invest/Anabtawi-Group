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

function readFileAsBase64(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result);
        reader.onerror = () => reject(reader.error || new Error("Could not read file"));
        reader.readAsDataURL(file);
    });
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

function showError(errorEl, message) {
    if (!errorEl) {
        return;
    }
    errorEl.textContent = message;
    errorEl.classList.remove("d-none");
}

function initCreatePage(root) {
    const nameInput = qs("#customer_name", root);
    const phoneInput = qs("#customer_phone", root);
    const emailInput = qs("#customer_email", root);
    const vatInput = qs("#customer_vat", root);
    const typeInput = qs("#customer_type", root);
    const fileInput = qs("#customer_attachment", root);
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
        const vat = (vatInput && vatInput.value) || "";
        const contactType = (typeInput && typeInput.value) || "person";
        const file = fileInput && fileInput.files && fileInput.files[0];

        if (!name.trim()) {
            showError(errorEl, "Customer name is required.");
            return;
        }
        if (!phone.trim()) {
            showError(errorEl, "Phone is required.");
            return;
        }
        if (!vat.trim()) {
            showError(errorEl, "Tax ID (VAT) is required.");
            return;
        }
        if (!file) {
            showError(errorEl, "At least one document attachment is required.");
            return;
        }

        submitBtn.disabled = true;
        try {
            const datas = await readFileAsBase64(file);
            const result = await submitRequest({
                name,
                phone,
                email,
                vat,
                contact_type: contactType,
                attachment: {
                    name: file.name,
                    datas,
                },
            });
            window.location.href = result.redirect_url || "/my/customer-requests";
        } catch (err) {
            showError(errorEl, errorMessage(err));
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
            showError(errorEl, errorMessage(err));
            cancelBtn.disabled = false;
        }
    });
}
