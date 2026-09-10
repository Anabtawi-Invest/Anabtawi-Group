/** @odoo-module **/

import { rpc } from "@web/core/network/rpc";

function qs(sel, root = document) {
    return root.querySelector(sel);
}

function qsa(sel, root = document) {
    return [...root.querySelectorAll(sel)];
}

function money(n) {
    return (Number(n) || 0).toFixed(2);
}

document.addEventListener("DOMContentLoaded", start);
if (document.readyState !== "loading") {
    start();
}

function start() {
    if (window.__portalSaleOrderInit) {
        return;
    }
    window.__portalSaleOrderInit = true;
    const createRoot = qs(".o_portal_sale_create");
    if (createRoot) {
        initCreatePage(createRoot);
    }
    initDetailPage();
}

function initCreatePage(root) {
    const state = {
        partner: null,
        cart: {}, // product_id -> {id,name,price,qty}
    };

    const partnerSearch = qs("#partner_search", root);
    const partnerResults = qs("#partner_results", root);
    const selectedBox = qs("#selected_partner", root);
    const selectedLabel = qs("#selected_partner_label", root);
    const newForm = qs("#new_partner_form", root);
    const cartBody = qs("#cart_body", root);
    const cartEmpty = qs("#cart_empty", root);
    const cartWrap = qs("#cart_table_wrap", root);
    const cartTotal = qs("#cart_total", root);
    const confirmError = qs("#confirm_error", root);
    const productGrid = qs("#product_grid");
    const productSearch = qs("#product_search");
    const modalEl = qs("#productModal");

    let searchTimer = null;
    let productTimer = null;

    function selectPartner(partner) {
        state.partner = partner;
        selectedLabel.textContent = `${partner.name}${partner.phone ? " — " + partner.phone : ""}${partner.email ? " — " + partner.email : ""}`;
        selectedBox.classList.remove("d-none");
        partnerResults.innerHTML = "";
        partnerSearch.value = "";
        newForm.classList.add("d-none");
    }

    function renderCart() {
        const items = Object.values(state.cart);
        if (!items.length) {
            cartEmpty.classList.remove("d-none");
            cartWrap.classList.add("d-none");
            cartBody.innerHTML = "";
            cartTotal.textContent = "0.00";
            return;
        }
        cartEmpty.classList.add("d-none");
        cartWrap.classList.remove("d-none");
        let total = 0;
        cartBody.innerHTML = items
            .map((item) => {
                const sub = item.price * item.qty;
                total += sub;
                return `<tr data-id="${item.id}">
                    <td>${escapeHtml(item.name)}</td>
                    <td class="text-end">${money(item.price)}</td>
                    <td class="text-center">
                        <input type="number" min="0.01" step="1" class="form-control form-control-sm cart-qty" value="${item.qty}"/>
                    </td>
                    <td class="text-end">${money(sub)}</td>
                    <td class="text-end">
                        <button type="button" class="btn btn-sm btn-outline-danger cart-remove">×</button>
                    </td>
                </tr>`;
            })
            .join("");
        cartTotal.textContent = money(total);

        qsa(".cart-qty", cartBody).forEach((input) => {
            input.addEventListener("change", () => {
                const tr = input.closest("tr");
                const id = tr.dataset.id;
                const qty = parseFloat(input.value) || 0;
                if (qty <= 0) {
                    delete state.cart[id];
                } else {
                    state.cart[id].qty = qty;
                }
                renderCart();
            });
        });
        qsa(".cart-remove", cartBody).forEach((btn) => {
            btn.addEventListener("click", () => {
                const id = btn.closest("tr").dataset.id;
                delete state.cart[id];
                renderCart();
            });
        });
    }

    async function searchPartners(term) {
        const partners = await rpc("/my/sales/api/partners", { term });
        if (!partners.length) {
            partnerResults.innerHTML = `<div class="list-group-item text-muted">No customers found</div>`;
            return;
        }
        partnerResults.innerHTML = partners
            .map(
                (p) => `<button type="button" class="list-group-item list-group-item-action"
                    data-id="${p.id}" data-name="${escapeAttr(p.name)}"
                    data-phone="${escapeAttr(p.phone)}" data-email="${escapeAttr(p.email)}">
                    <strong>${escapeHtml(p.name)}</strong>
                    <div class="small text-muted">${escapeHtml(p.phone || "")} ${escapeHtml(p.email || "")}</div>
                </button>`
            )
            .join("");
        qsa("button", partnerResults).forEach((btn) => {
            btn.addEventListener("click", () => {
                selectPartner({
                    id: parseInt(btn.dataset.id, 10),
                    name: btn.dataset.name,
                    phone: btn.dataset.phone,
                    email: btn.dataset.email,
                });
            });
        });
    }

    async function loadProducts(term = "") {
        productGrid.innerHTML = `<div class="text-muted">Loading...</div>`;
        const products = await rpc("/my/sales/api/products", { term });
        if (!products.length) {
            productGrid.innerHTML = `<div class="text-muted">No products found</div>`;
            return;
        }
        productGrid.innerHTML = products
            .map((p) => {
                const inCart = state.cart[p.id];
                return `<div class="o_portal_product_card" data-id="${p.id}">
                    <img src="${p.image_url}" alt=""/>
                    <div class="o_product_name">${escapeHtml(p.name)}</div>
                    <div class="o_product_price">${escapeHtml(p.price_display)}</div>
                    <div class="o_qty_row">
                        <input type="number" min="1" step="1" value="${inCart ? inCart.qty : 1}" class="form-control form-control-sm product-qty"/>
                        <button type="button" class="btn btn-sm btn-primary product-add">Add</button>
                    </div>
                </div>`;
            })
            .join("");

        qsa(".o_portal_product_card", productGrid).forEach((card) => {
            const product = products.find((p) => String(p.id) === card.dataset.id);
            qs(".product-add", card).addEventListener("click", () => {
                const qty = parseFloat(qs(".product-qty", card).value) || 1;
                state.cart[product.id] = {
                    id: product.id,
                    name: product.name,
                    price: product.price,
                    qty,
                };
                renderCart();
                qs(".product-add", card).textContent = "Added";
                qs(".product-add", card).classList.replace("btn-primary", "btn-success");
            });
        });
    }

    partnerSearch.addEventListener("input", () => {
        clearTimeout(searchTimer);
        const term = partnerSearch.value.trim();
        if (term.length < 1) {
            partnerResults.innerHTML = "";
            return;
        }
        searchTimer = setTimeout(() => searchPartners(term), 300);
    });

    qs("#btn_new_partner", root).addEventListener("click", () => {
        newForm.classList.toggle("d-none");
    });

    qs("#btn_clear_partner", root).addEventListener("click", () => {
        state.partner = null;
        selectedBox.classList.add("d-none");
    });

    qs("#btn_save_partner", root).addEventListener("click", async () => {
        confirmError.classList.add("d-none");
        try {
            const partner = await rpc("/my/sales/api/partner/create", {
                name: qs("#new_partner_name", root).value,
                phone: qs("#new_partner_phone", root).value,
                email: qs("#new_partner_email", root).value,
            });
            selectPartner(partner);
            qs("#new_partner_name", root).value = "";
            qs("#new_partner_phone", root).value = "";
            qs("#new_partner_email", root).value = "";
        } catch (e) {
            showError(confirmError, e);
        }
    });

    qs("#btn_open_products", root).addEventListener("click", async () => {
        if (window.bootstrap && modalEl) {
            bootstrap.Modal.getOrCreateInstance(modalEl).show();
        } else {
            modalEl.classList.add("show");
            modalEl.style.display = "block";
        }
        await loadProducts();
    });

    productSearch.addEventListener("input", () => {
        clearTimeout(productTimer);
        productTimer = setTimeout(() => loadProducts(productSearch.value.trim()), 300);
    });

    qs("#btn_confirm_order", root).addEventListener("click", async () => {
        confirmError.classList.add("d-none");
        if (!state.partner) {
            showError(confirmError, "Please select a customer.");
            return;
        }
        const lines = Object.values(state.cart).map((i) => ({ product_id: i.id, qty: i.qty }));
        if (!lines.length) {
            showError(confirmError, "Please add at least one product.");
            return;
        }
        const btn = qs("#btn_confirm_order", root);
        btn.disabled = true;
        try {
            const result = await rpc("/my/sales/api/confirm", {
                partner_id: state.partner.id,
                lines,
            });
            window.location.href = result.redirect_url;
        } catch (e) {
            showError(confirmError, e);
            btn.disabled = false;
        }
    });
}

function initDetailPage() {
    const msg = qs("#detail_message");
    const emailBtn = qs("#btn_send_email");
    const cancelBtn = qs("#btn_cancel_order");

    if (emailBtn) {
        emailBtn.addEventListener("click", async () => {
            try {
                const res = await rpc("/my/sales/api/send_email", {
                    order_id: parseInt(emailBtn.dataset.orderId, 10),
                });
                showMessage(msg, res.message || "Sent.", "success");
            } catch (e) {
                showMessage(msg, extractError(e), "danger");
            }
        });
    }

    if (cancelBtn) {
        cancelBtn.addEventListener("click", async () => {
            if (!window.confirm("Cancel this order and reverse its invoice?")) {
                return;
            }
            try {
                const res = await rpc("/my/sales/api/cancel", {
                    order_id: parseInt(cancelBtn.dataset.orderId, 10),
                });
                showMessage(msg, res.message || "Cancelled.", "success");
                window.location.reload();
            } catch (e) {
                showMessage(msg, extractError(e), "danger");
            }
        });
    }
}

function showError(el, err) {
    el.textContent = extractError(err);
    el.classList.remove("d-none");
}

function showMessage(el, text, type) {
    if (!el) return;
    el.className = `alert alert-${type} mt-3 mb-0`;
    el.textContent = text;
    el.classList.remove("d-none");
}

function extractError(err) {
    if (!err) return "Unexpected error";
    if (typeof err === "string") return err;
    return err.data?.message || err.message || String(err);
}

function escapeHtml(str) {
    return String(str || "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
}

function escapeAttr(str) {
    return escapeHtml(str).replace(/'/g, "&#39;");
}
