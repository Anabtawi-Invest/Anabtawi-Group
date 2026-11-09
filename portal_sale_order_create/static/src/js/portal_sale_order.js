/** @odoo-module **/

import { whenReady } from "@odoo/owl";
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

whenReady().then(start);
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

async function fetchPartners(term, saleMode) {
    const mode = saleMode || "cash";
    try {
        return await rpc("/my/sales/api/partners", { term, sale_mode: mode });
    } catch (e1) {
        const url =
            `/my/sales/api/partners/http?term=${encodeURIComponent(term)}` +
            `&sale_mode=${encodeURIComponent(mode)}`;
        const response = await fetch(url, { credentials: "same-origin" });
        if (!response.ok) {
            throw e1;
        }
        return await response.json();
    }
}

async function createCashCustomer(payload) {
    try {
        return await rpc("/my/sales/api/cash_customers/create", payload);
    } catch (e1) {
        if (e1 && e1.data && e1.data.message) {
            throw e1;
        }
        const response = await fetch("/my/sales/api/cash_customers/create/http", {
            method: "POST",
            credentials: "same-origin",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        });
        if (!response.ok) {
            throw e1;
        }
        const result = await response.json();
        if (result && result.error) {
            throw result.error;
        }
        return result.result !== undefined ? result.result : result;
    }
}

async function fetchPaymentTerms() {
    try {
        return await rpc("/my/sales/api/payment_terms", {});
    } catch (e1) {
        const response = await fetch("/my/sales/api/payment_terms/http", {
            credentials: "same-origin",
        });
        if (!response.ok) {
            throw e1;
        }
        return await response.json();
    }
}

function initCreatePage(root) {
    const saleMode = (root.dataset.saleMode || "cash").toLowerCase();
    const isCredit = saleMode === "credit";
    const state = {
        partner: null,
        paymentTermId: null,
        paymentTermsLoaded: false,
        cart: {},
        productOffset: 0,
        productTerm: "",
        productTotal: 0,
    };

    const partnerSearch = qs("#partner_search", root);
    const partnerResults = qs("#partner_results", root);
    const selectedBox = qs("#selected_partner", root);
    const selectedLabel = qs("#selected_partner_label", root);
    const paymentTermWrap = qs("#payment_term_wrap", root);
    const paymentTermSelect = qs("#payment_term_id", root);
    const cashNameInput = qs("#cash_customer_name", root);
    const cashPhoneInput = qs("#cash_customer_phone", root);
    const cashEmailInput = qs("#cash_customer_email", root);
    const cashCreateBtn = qs("#btn_create_cash_customer", root);
    const cashCreateError = qs("#cash_customer_error", root);
    const cartBody = qs("#cart_body", root);
    const cartEmpty = qs("#cart_empty", root);
    const cartWrap = qs("#cart_table_wrap", root);
    const cartTotal = qs("#cart_total", root);
    const confirmError = qs("#confirm_error", root);
    const productGrid = qs("#product_grid");
    const productSearch = qs("#product_search");
    const productCount = qs("#product_count");
    const loadMoreBtn = qs("#btn_load_more_products");
    const doneBtn = qs("#btn_done_products");
    const closeBtn = qs("#btn_close_products");
    const closeBackdrop = qs("#btn_close_products_backdrop");
    const modalEl = qs("#productModal");
    const PAGE_SIZE = 60;

    let searchTimer = null;
    let productTimer = null;
    let searchSeq = 0;

    if (!partnerSearch || !partnerResults) {
        console.error("portal_sale_order_create: partner search elements missing");
        return;
    }

    function openModal() {
        if (!modalEl) {
            return;
        }
        modalEl.classList.remove("d-none");
        modalEl.setAttribute("aria-hidden", "false");
        document.body.classList.add("o_portal_sale_dialog_open");
    }

    function closeModal() {
        if (!modalEl) {
            return;
        }
        modalEl.classList.add("d-none");
        modalEl.setAttribute("aria-hidden", "true");
        document.body.classList.remove("o_portal_sale_dialog_open");
        renderCart();
    }

    function hidePartnerResults() {
        partnerResults.innerHTML = "";
    }

    function cancelPartnerSearch() {
        clearTimeout(searchTimer);
        searchSeq += 1;
        hidePartnerResults();
    }

    const partnerSearchWrap = partnerSearch.closest(".o_portal_partner_autocomplete");

    function hidePaymentTerms() {
        state.paymentTermId = null;
        if (!isCredit && paymentTermWrap) {
            paymentTermWrap.classList.add("d-none");
        }
        if (paymentTermSelect) {
            paymentTermSelect.value = "";
        }
    }

    async function ensurePaymentTermsOptions() {
        if (!paymentTermSelect || state.paymentTermsLoaded) {
            return;
        }
        const terms = await fetchPaymentTerms();
        const options = ['<option value="">Select payment terms...</option>'].concat(
            (terms || []).map(
                (term) =>
                    `<option value="${term.id}">${escapeHtml(term.name)}</option>`
            )
        );
        paymentTermSelect.innerHTML = options.join("");
        state.paymentTermsLoaded = true;
    }

    async function showPaymentTerms(partner) {
        if (!isCredit || !paymentTermWrap || !paymentTermSelect) {
            return;
        }
        await ensurePaymentTermsOptions();
        paymentTermWrap.classList.remove("d-none");
        const defaultId = partner.default_payment_term_id
            ? String(partner.default_payment_term_id)
            : "";
        if (defaultId && paymentTermSelect.querySelector(`option[value="${defaultId}"]`)) {
            paymentTermSelect.value = defaultId;
            state.paymentTermId = partner.default_payment_term_id;
        } else {
            paymentTermSelect.value = "";
            state.paymentTermId = null;
        }
    }

    function selectPartner(partner) {
        state.partner = partner;
        selectedLabel.textContent = `${partner.name}${partner.phone ? " — " + partner.phone : ""}${partner.email ? " — " + partner.email : ""}`;
        selectedBox.classList.remove("d-none");
        partnerSearch.value = "";
        // Drop pending/in-flight searches so results don't reopen after click.
        cancelPartnerSearch();
        if (partnerSearchWrap) {
            partnerSearchWrap.classList.add("d-none");
        }
        if (isCredit) {
            showPaymentTerms(partner).catch((err) => {
                console.error("portal_sale_order_create: failed to load payment terms", err);
                hidePaymentTerms();
            });
        } else {
            hidePaymentTerms();
        }
    }

    if (isCredit) {
        ensurePaymentTermsOptions().catch((err) => {
            console.error("portal_sale_order_create: failed to preload payment terms", err);
        });
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
                const maxAttr =
                    item.qty_available != null
                        ? ` max="${item.qty_available}"`
                        : "";
                return `<tr data-id="${item.id}">
                    <td>${escapeHtml(item.name)}</td>
                    <td class="text-end">${money(item.price)}</td>
                    <td class="text-center">
                        <input type="number" min="0.01" step="1" class="form-control form-control-sm cart-qty" value="${item.qty}"${maxAttr}/>
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
                const id = input.closest("tr").dataset.id;
                let qty = parseFloat(input.value) || 0;
                const maxQty = state.cart[id]?.qty_available;
                if (maxQty != null && qty > maxQty) {
                    qty = maxQty;
                    input.value = String(maxQty);
                }
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
                delete state.cart[btn.closest("tr").dataset.id];
                renderCart();
            });
        });
    }

    async function searchPartners(term) {
        const seq = ++searchSeq;
        partnerResults.innerHTML = `<div class="list-group-item text-muted">جاري البحث... / Searching...</div>`;
        try {
            const partners = await fetchPartners(term, saleMode);
            if (seq !== searchSeq) {
                return;
            }
            if (!partners.length) {
                partnerResults.innerHTML = isCredit
                    ? `
                    <div class="list-group-item o_portal_partner_empty">
                        <div class="fw-semibold mb-1">لا يوجد عميل مطابق</div>
                        <div class="small text-muted mb-0">
                            No credit customer found with you as salesperson.
                            <a href="/my/customer-requests/create">Request Credit Customer</a>
                        </div>
                    </div>`
                    : `
                    <div class="list-group-item o_portal_partner_empty">
                        <div class="fw-semibold mb-1">لا يوجد عميل مطابق</div>
                        <div class="small text-muted mb-0">
                            No walk-in customer found under your van customer.
                            Create one using the form below.
                        </div>
                    </div>`;
                return;
            }
            const safeTerm = term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
            const re = safeTerm ? new RegExp(`(${safeTerm})`, "ig") : null;
            const highlight = (text) => {
                const value = String(text || "");
                if (!re || !value) {
                    return escapeHtml(value);
                }
                return escapeHtml(value).replace(re, "<mark>$1</mark>");
            };
            partnerResults.innerHTML = partners
                .map(
                    (p) => `<button type="button" class="list-group-item list-group-item-action text-start"
                        data-id="${p.id}" data-name="${escapeAttr(p.name)}"
                        data-phone="${escapeAttr(p.phone)}" data-email="${escapeAttr(p.email)}"
                        data-allow-payment-term="${p.portal_allow_payment_term ? "1" : "0"}"
                        data-default-payment-term-id="${p.default_payment_term_id || ""}">
                        <strong>${highlight(p.name)}</strong>
                        <div class="small text-muted">
                            ${p.phone ? highlight(p.phone) : ""}
                            ${p.email ? " · " + highlight(p.email) : ""}
                        </div>
                    </button>`
                )
                .join("");
            qsa("button", partnerResults).forEach((btn) => {
                const pick = (ev) => {
                    ev.preventDefault();
                    ev.stopPropagation();
                    const defaultTerm = parseInt(btn.dataset.defaultPaymentTermId || "", 10);
                    selectPartner({
                        id: parseInt(btn.dataset.id, 10),
                        name: btn.dataset.name,
                        phone: btn.dataset.phone,
                        email: btn.dataset.email,
                        portal_allow_payment_term: btn.dataset.allowPaymentTerm === "1",
                        default_payment_term_id: defaultTerm || false,
                    });
                };
                // mousedown avoids blur-before-click; click covers touch / keyboard activate.
                btn.addEventListener("mousedown", pick);
                btn.addEventListener("click", pick);
            });
        } catch (e) {
            if (seq !== searchSeq) {
                return;
            }
            partnerResults.innerHTML = `
                <div class="list-group-item o_portal_partner_empty">
                    <div class="fw-semibold mb-1">لا يوجد عميل مطابق</div>
                    <div class="small text-muted mb-0">
                        Search failed. Try another name, phone or email.
                    </div>
                </div>`;
        }
    }

    function schedulePartnerSearch() {
        clearTimeout(searchTimer);
        if (state.partner) {
            hidePartnerResults();
            return;
        }
        const term = partnerSearch.value.trim();
        if (term.length < 1) {
            hidePartnerResults();
            return;
        }
        searchTimer = setTimeout(() => searchPartners(term), 120);
    }

    function bindProductCard(card, product) {
        const qtyInput = qs(".product-qty", card);
        const maxQty = product.qty_available != null && product.qty_available !== false
            ? Number(product.qty_available)
            : null;
        if (qtyInput && maxQty != null) {
            qtyInput.max = String(maxQty);
            qtyInput.addEventListener("change", () => {
                let qty = parseFloat(qtyInput.value) || 1;
                if (qty > maxQty) {
                    qty = maxQty;
                    qtyInput.value = String(maxQty);
                }
                if (qty < 1) {
                    qtyInput.value = "1";
                }
            });
        }
        qs(".product-add", card).addEventListener("click", () => {
            let qty = parseFloat(qs(".product-qty", card).value) || 1;
            if (maxQty != null) {
                if (maxQty <= 0) {
                    return;
                }
                if (qty > maxQty) {
                    qty = maxQty;
                    qs(".product-qty", card).value = String(maxQty);
                }
            }
            state.cart[product.id] = {
                id: product.id,
                name: product.name,
                price: product.price,
                qty,
                qty_available: maxQty,
            };
            renderCart();
            const addBtn = qs(".product-add", card);
            addBtn.textContent = "Added";
            addBtn.classList.remove("btn-primary");
            addBtn.classList.add("btn-success");
        });
    }

    function productCardHtml(p) {
        const inCart = state.cart[p.id];
        const hasStockInfo = p.qty_available != null && p.qty_available !== false;
        const stockLine = hasStockInfo
            ? `<div class="o_product_stock text-success small">Available: ${escapeHtml(p.qty_available_display || String(p.qty_available))}</div>`
            : "";
        const maxAttr = hasStockInfo ? ` max="${p.qty_available}"` : "";
        const startQty = inCart ? inCart.qty : 1;
        return `<div class="o_portal_product_card" data-id="${p.id}">
            <img src="${p.image_url}" alt="" loading="lazy"/>
            <div class="o_product_name">${escapeHtml(p.name)}</div>
            <div class="o_product_price">${escapeHtml(p.price_display)}</div>
            ${stockLine}
            <div class="o_qty_row">
                <input type="number" min="1" step="1" value="${startQty}"${maxAttr} class="form-control form-control-sm product-qty"/>
                <button type="button" class="btn btn-sm ${inCart ? "btn-success" : "btn-primary"} product-add">
                    ${inCart ? "Added" : "Add"}
                </button>
            </div>
        </div>`;
    }

    function updateProductMeta(hasMore) {
        if (productCount) {
            const shown = productGrid.querySelectorAll(".o_portal_product_card").length;
            productCount.textContent = state.productTotal
                ? `Showing ${shown} of ${state.productTotal} products`
                : "";
        }
        if (loadMoreBtn) {
            loadMoreBtn.classList.toggle("d-none", !hasMore);
            loadMoreBtn.disabled = false;
            loadMoreBtn.textContent = "Load more products";
        }
    }

    async function loadProducts({ reset = true } = {}) {
        if (reset) {
            state.productOffset = 0;
            productGrid.innerHTML = `<div class="text-muted">Loading...</div>`;
            if (loadMoreBtn) {
                loadMoreBtn.classList.add("d-none");
            }
        } else if (loadMoreBtn) {
            loadMoreBtn.disabled = true;
            loadMoreBtn.textContent = "Loading...";
        }

        const payload = await rpc("/my/sales/api/products", {
            term: state.productTerm,
            offset: state.productOffset,
            limit: PAGE_SIZE,
        });
        const products = Array.isArray(payload) ? payload : payload.products || [];
        const total = Array.isArray(payload) ? products.length : payload.total || 0;
        const hasMore = Array.isArray(payload) ? false : Boolean(payload.has_more);

        state.productTotal = total;
        state.productOffset += products.length;

        if (reset && !products.length) {
            productGrid.innerHTML = `<div class="text-muted">No products found</div>`;
            updateProductMeta(false);
            return;
        }

        const html = products.map(productCardHtml).join("");
        if (reset) {
            productGrid.innerHTML = html;
        } else {
            productGrid.insertAdjacentHTML("beforeend", html);
        }

        products.forEach((product) => {
            const card = productGrid.querySelector(`.o_portal_product_card[data-id="${product.id}"]`);
            if (card) {
                bindProductCard(card, product);
            }
        });
        updateProductMeta(hasMore);
    }

    partnerSearch.addEventListener("input", schedulePartnerSearch);
    partnerSearch.addEventListener("keyup", schedulePartnerSearch);
    partnerSearch.addEventListener("compositionend", schedulePartnerSearch);
    partnerSearch.addEventListener("focus", schedulePartnerSearch);

    qs("#btn_clear_partner", root)?.addEventListener("click", () => {
        state.partner = null;
        selectedBox?.classList.add("d-none");
        cancelPartnerSearch();
        if (partnerSearchWrap) {
            partnerSearchWrap.classList.remove("d-none");
        }
        partnerSearch.focus();
        hidePaymentTerms();
    });

    if (paymentTermSelect) {
        paymentTermSelect.addEventListener("change", () => {
            const value = paymentTermSelect.value;
            state.paymentTermId = value ? parseInt(value, 10) : null;
        });
    }

    qs("#btn_open_products", root).addEventListener("click", async () => {
        openModal();
        state.productTerm = (productSearch?.value || "").trim();
        await loadProducts({ reset: true });
    });

    if (productSearch) {
        productSearch.addEventListener("input", () => {
            clearTimeout(productTimer);
            productTimer = setTimeout(() => {
                state.productTerm = productSearch.value.trim();
                loadProducts({ reset: true });
            }, 300);
        });
    }

    if (loadMoreBtn) {
        loadMoreBtn.addEventListener("click", () => loadProducts({ reset: false }));
    }
    if (doneBtn) {
        doneBtn.addEventListener("click", (ev) => {
            ev.preventDefault();
            closeModal();
        });
    }
    if (closeBtn) {
        closeBtn.addEventListener("click", (ev) => {
            ev.preventDefault();
            closeModal();
        });
    }
    if (closeBackdrop) {
        closeBackdrop.addEventListener("click", (ev) => {
            ev.preventDefault();
            closeModal();
        });
    }
    document.addEventListener("keydown", (ev) => {
        if (ev.key === "Escape" && modalEl && !modalEl.classList.contains("d-none")) {
            closeModal();
        }
    });

    if (cashCreateBtn) {
        cashCreateBtn.addEventListener("click", async () => {
            if (cashCreateError) {
                cashCreateError.classList.add("d-none");
                cashCreateError.textContent = "";
            }
            const name = (cashNameInput && cashNameInput.value) || "";
            if (!name.trim()) {
                if (cashCreateError) {
                    cashCreateError.textContent = "Customer name is required.";
                    cashCreateError.classList.remove("d-none");
                }
                return;
            }
            cashCreateBtn.disabled = true;
            try {
                const partner = await createCashCustomer({
                    name,
                    phone: (cashPhoneInput && cashPhoneInput.value) || "",
                    email: (cashEmailInput && cashEmailInput.value) || "",
                });
                if (cashNameInput) cashNameInput.value = "";
                if (cashPhoneInput) cashPhoneInput.value = "";
                if (cashEmailInput) cashEmailInput.value = "";
                selectPartner(partner);
            } catch (err) {
                if (cashCreateError) {
                    cashCreateError.textContent = extractError(err);
                    cashCreateError.classList.remove("d-none");
                }
            } finally {
                cashCreateBtn.disabled = false;
            }
        });
    }

    qs("#btn_confirm_order", root).addEventListener("click", async () => {
        confirmError.classList.add("d-none");
        if (!state.partner) {
            showError(confirmError, "Please select a customer.");
            return;
        }
        if (isCredit && !state.paymentTermId) {
            showError(confirmError, "Please select payment terms.");
            return;
        }
        const lines = Object.values(state.cart).map((i) => ({ product_id: i.id, qty: i.qty }));
        if (!lines.length) {
            showError(confirmError, "Please add at least one product.");
            return;
        }
        for (const item of Object.values(state.cart)) {
            if (item.qty_available != null && item.qty > item.qty_available) {
                showError(
                    confirmError,
                    `Not enough stock for ${item.name}. Available: ${item.qty_available}.`
                );
                return;
            }
        }
        const btn = qs("#btn_confirm_order", root);
        btn.disabled = true;
        try {
            const payload = {
                partner_id: state.partner.id,
                lines,
                sale_mode: saleMode,
            };
            if (isCredit) {
                payload.payment_term_id = state.paymentTermId;
            }
            const result = await rpc("/my/sales/api/confirm", payload);
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
            const isDraft = cancelBtn.dataset.isDraft === "1";
            const confirmMsg = isDraft
                ? "Cancel this draft quotation?"
                : "Cancel this order and reverse its invoice?";
            if (!window.confirm(confirmMsg)) {
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
