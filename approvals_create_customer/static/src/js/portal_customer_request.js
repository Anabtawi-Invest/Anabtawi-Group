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

function readFileAsBase64(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => {
            const result = reader.result || "";
            const datas = String(result).includes(",")
                ? String(result).split(",", 1)[1]
                : String(result);
            resolve({
                name: file.name,
                mimetype: file.type || "application/octet-stream",
                datas,
            });
        };
        reader.onerror = () => reject(reader.error || new Error("Could not read file"));
        reader.readAsDataURL(file);
    });
}

function formatFileSize(size) {
    if (size < 1024) {
        return `${size} B`;
    }
    if (size < 1024 * 1024) {
        return `${(size / 1024).toFixed(1)} KB`;
    }
    return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

function initCreatePage(root) {
    const nameInput = qs("#customer_name", root);
    const phoneInput = qs("#customer_phone", root);
    const emailInput = qs("#customer_email", root);
    const fileInput = qs("#commercial_register_files", root);
    const fileList = qs("#commercial_register_file_list", root);
    const submitBtn = qs("#btn_submit_customer_request", root);
    const errorEl = qs("#submit_error", root);
    let selectedFiles = [];

    if (!submitBtn) {
        return;
    }

    function renderFileList() {
        if (!fileList) {
            return;
        }
        if (!selectedFiles.length) {
            fileList.classList.add("d-none");
            fileList.innerHTML = "";
            return;
        }
        fileList.classList.remove("d-none");
        fileList.innerHTML = selectedFiles
            .map(
                (file, index) => `
                <li class="list-group-item d-flex justify-content-between align-items-center gap-2">
                    <span class="text-truncate">${file.name} <span class="text-muted">(${formatFileSize(file.size)})</span></span>
                    <button type="button" class="btn btn-sm btn-outline-danger" data-remove-index="${index}">Remove</button>
                </li>`
            )
            .join("");
    }

    if (fileInput) {
        fileInput.addEventListener("change", () => {
            const incoming = Array.from(fileInput.files || []);
            const existingNames = new Set(selectedFiles.map((f) => `${f.name}:${f.size}`));
            incoming.forEach((file) => {
                const key = `${file.name}:${file.size}`;
                if (!existingNames.has(key)) {
                    selectedFiles.push(file);
                    existingNames.add(key);
                }
            });
            fileInput.value = "";
            renderFileList();
        });
    }

    if (fileList) {
        fileList.addEventListener("click", (ev) => {
            const btn = ev.target.closest("[data-remove-index]");
            if (!btn) {
                return;
            }
            const index = parseInt(btn.dataset.removeIndex, 10);
            if (Number.isNaN(index)) {
                return;
            }
            selectedFiles.splice(index, 1);
            renderFileList();
        });
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
        if (!selectedFiles.length) {
            if (errorEl) {
                errorEl.textContent =
                    "Please attach at least one Commercial Register (السجل التجاري) document.";
                errorEl.classList.remove("d-none");
            }
            return;
        }
        submitBtn.disabled = true;
        try {
            const attachments = [];
            for (const file of selectedFiles) {
                attachments.push(await readFileAsBase64(file));
            }
            const result = await submitRequest({ name, phone, email, attachments });
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
