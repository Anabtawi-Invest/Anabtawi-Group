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
        cart: {},
        productOffset: 0,
        productTerm: "",
        productTotal: 0,
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
    const productCount = qs("#product_count");
    const loadMoreBtn = qs("#btn_load_more_products");
    const doneBtn = qs("#btn_done_products");
    const closeBtn = qs("#btn_close_products");
    const closeBackdrop = qs("#btn_close_products_backdrop");
    const modalEl = qs("#productModal");
    const PAGE_SIZE = 60;

    let searchTimer = null;
    let productTimer = null;

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
        const productsSection = qs(".o_portal_sale_section #cart_table_wrap", root) || qs(".o_portal_sale_section", root);
        if (productsSection) {
            productsSection.scrollIntoView({ behavior: "smooth", block: "center" });
        }
    }

    function selectPartner(partner) {
        state.partner = partner;
        selectedLabel.textContent = `${partner.name}${partner.phone ? " — " + partner.phone : ""}${partner.email ? " — " + partner.email : ""}`;
        selectedBox.classList.remove("d-none");
        partnerSearch.value = "";
        newForm.classList.add("d-none");
        hidePartnerResults();
    }

    function hidePartnerResults() {
        partnerResults.classList.add("d-none");
        partnerResults.innerHTML = "";
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
        partnerResults.classList.remove("d-none");
        partnerResults.innerHTML = `<div class="list-group-item text-muted">Searching...</div>`;
        try {
            const partners = await rpc("/my/sales/api/partners", { term });
            if (!partners.length) {
                partnerResults.innerHTML = `<div class="list-group-item text-muted">No customers found</div>`;
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
                    (p) => `<button type="button" class="list-group-item list-group-item-action"
                        data-id="${p.id}" data-name="${escapeAttr(p.name)}"
                        data-phone="${escapeAttr(p.phone)}" data-email="${escapeAttr(p.email)}">
                        <strong>${highlight(p.name)}</strong>
                        <div class="small text-muted">
                            ${p.phone ? highlight(p.phone) : ""}
                            ${p.email ? " · " + highlight(p.email) : ""}
                        </div>
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
        } catch (e) {
            partnerResults.innerHTML = `<div class="list-group-item text-danger">${escapeHtml(extractError(e))}</div>`;
        }
    }

    function bindProductCard(card, product) {
        qs(".product-add", card).addEventListener("click", () => {
            const qty = parseFloat(qs(".product-qty", card).value) || 1;
            state.cart[product.id] = {
                id: product.id,
                name: product.name,
                price: product.price,
                qty,
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
        return `<div class="o_portal_product_card" data-id="${p.id}">
            <img src="${p.image_url}" alt="" loading="lazy"/>
            <div class="o_product_name">${escapeHtml(p.name)}</div>
            <div class="o_product_price">${escapeHtml(p.price_display)}</div>
            <div class="o_qty_row">
                <input type="number" min="1" step="1" value="${inCart ? inCart.qty : 1}" class="form-control form-control-sm product-qty"/>
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

    partnerSearch.addEventListener("input", () => {
        clearTimeout(searchTimer);
        const term = partnerSearch.value.trim();
        if (term.length < 1) {
            hidePartnerResults();
            return;
        }
        // Show choices as soon as the user types the first letter(s)
        searchTimer = setTimeout(() => searchPartners(term), 150);
    });

    partnerSearch.addEventListener("focus", () => {
        const term = partnerSearch.value.trim();
        if (term.length >= 1) {
            searchPartners(term);
        }
    });

    document.addEventListener("click", (ev) => {
        const box = qs(".o_portal_partner_autocomplete", root);
        if (box && !box.contains(ev.target)) {
            hidePartnerResults();
        }
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

    // Explicit close handlers — no Bootstrap Modal
    if (doneBtn) {
        doneBtn.addEventListener("click", (ev) => {
            ev.preventDefault();
            ev.stopPropagation();
            closeModal();
        });
    }
    if (closeBtn) {
        closeBtn.addEventListener("click", (ev) => {
            ev.preventDefault();
            ev.stopPropagation();
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
