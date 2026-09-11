/** @odoo-module **/

import { whenReady } from "@odoo/owl";
import { rpc } from "@web/core/network/rpc";

function qs(sel, root = document) {
    return root.querySelector(sel);
}

function qsa(sel, root = document) {
    return [...root.querySelectorAll(sel)];
}

whenReady().then(start);
document.addEventListener("DOMContentLoaded", start);
if (document.readyState !== "loading") {
    start();
}

function start() {
    if (window.__portalInternalTransferInit) {
        return;
    }
    window.__portalInternalTransferInit = true;
    const createRoot = qs(".o_portal_transfer_create");
    if (createRoot) {
        initCreatePage(createRoot);
    }
    initDetailPage();
}

async function fetchLocations(term) {
    try {
        return await rpc("/my/transfers/api/locations", { term });
    } catch (e1) {
        const url = `/my/transfers/api/locations/http?term=${encodeURIComponent(term)}`;
        const response = await fetch(url, { credentials: "same-origin" });
        if (!response.ok) {
            throw e1;
        }
        return await response.json();
    }
}

function initCreatePage(root) {
    const state = {
        locationSrc: null,
        locationDest: null,
        cart: {},
        productOffset: 0,
        productTerm: "",
        productTotal: 0,
    };

    const cartBody = qs("#cart_body", root);
    const cartEmpty = qs("#cart_empty", root);
    const cartWrap = qs("#cart_table_wrap", root);
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

    let productTimer = null;

    function openModal() {
        if (!modalEl) return;
        modalEl.classList.remove("d-none");
        modalEl.setAttribute("aria-hidden", "false");
        document.body.classList.add("o_portal_transfer_dialog_open");
    }

    function closeModal() {
        if (!modalEl) return;
        modalEl.classList.add("d-none");
        modalEl.setAttribute("aria-hidden", "true");
        document.body.classList.remove("o_portal_transfer_dialog_open");
        renderCart();
    }

    function setupLocationSearch(opts) {
        const {
            inputId,
            resultsId,
            selectedId,
            labelId,
            clearId,
            stateKey,
            prefix,
        } = opts;
        const input = qs(inputId, root);
        const results = qs(resultsId, root);
        const selectedBox = qs(selectedId, root);
        const selectedLabel = qs(labelId, root);
        const clearBtn = qs(clearId, root);
        let timer = null;
        let seq = 0;

        function hideResults() {
            results.innerHTML = "";
        }

        function selectLocation(loc) {
            state[stateKey] = loc;
            selectedLabel.textContent = loc.name;
            selectedBox.classList.remove("d-none");
            input.value = "";
            hideResults();
        }

        async function search(term) {
            const current = ++seq;
            results.innerHTML = `<div class="list-group-item text-muted">Searching...</div>`;
            try {
                const locations = await fetchLocations(term);
                if (current !== seq) return;
                if (!locations.length) {
                    results.innerHTML = `
                        <div class="list-group-item text-muted">
                            <div class="fw-semibold">No matching location</div>
                            <div class="small">No internal location found for this search.</div>
                        </div>`;
                    return;
                }
                const safeTerm = term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
                const re = safeTerm ? new RegExp(`(${safeTerm})`, "ig") : null;
                const highlight = (text) => {
                    const value = String(text || "");
                    if (!re || !value) return escapeHtml(value);
                    return escapeHtml(value).replace(re, "<mark>$1</mark>");
                };
                results.innerHTML = locations
                    .map(
                        (loc) => `<button type="button" class="list-group-item list-group-item-action text-start"
                            data-id="${loc.id}" data-name="${escapeAttr(loc.name)}">
                            ${highlight(loc.name)}
                        </button>`
                    )
                    .join("");
                qsa("button", results).forEach((btn) => {
                    btn.addEventListener("mousedown", (ev) => {
                        ev.preventDefault();
                        selectLocation({
                            id: parseInt(btn.dataset.id, 10),
                            name: btn.dataset.name,
                        });
                    });
                });
            } catch (e) {
                if (current !== seq) return;
                results.innerHTML = `
                    <div class="list-group-item text-muted">
                        <div class="fw-semibold">No matching location</div>
                        <div class="small">Try another name.</div>
                    </div>`;
            }
        }

        function schedule() {
            clearTimeout(timer);
            const term = input.value.trim();
            if (term.length < 1) {
                hideResults();
                return;
            }
            timer = setTimeout(() => search(term), 120);
        }

        input.addEventListener("input", schedule);
        input.addEventListener("keyup", schedule);
        input.addEventListener("focus", schedule);
        clearBtn.addEventListener("click", () => {
            state[stateKey] = null;
            selectedBox.classList.add("d-none");
        });
    }

    setupLocationSearch({
        inputId: "#location_src_search",
        resultsId: "#location_src_results",
        selectedId: "#selected_location_src",
        labelId: "#selected_location_src_label",
        clearId: "#btn_clear_location_src",
        stateKey: "locationSrc",
        prefix: "From",
    });

    setupLocationSearch({
        inputId: "#location_dest_search",
        resultsId: "#location_dest_results",
        selectedId: "#selected_location_dest",
        labelId: "#selected_location_dest_label",
        clearId: "#btn_clear_location_dest",
        stateKey: "locationDest",
        prefix: "To",
    });

    function renderCart() {
        const items = Object.values(state.cart);
        if (!items.length) {
            cartEmpty.classList.remove("d-none");
            cartWrap.classList.add("d-none");
            cartBody.innerHTML = "";
            return;
        }
        cartEmpty.classList.add("d-none");
        cartWrap.classList.remove("d-none");
        cartBody.innerHTML = items
            .map(
                (item) => `<tr data-id="${item.id}">
                    <td>${escapeHtml(item.name)}</td>
                    <td class="text-center">
                        <input type="number" min="0.01" step="1" class="form-control form-control-sm cart-qty" value="${item.qty}"/>
                    </td>
                    <td class="text-end">
                        <button type="button" class="btn btn-sm btn-outline-danger cart-remove">×</button>
                    </td>
                </tr>`
            )
            .join("");

        qsa(".cart-qty", cartBody).forEach((input) => {
            input.addEventListener("change", () => {
                const id = input.closest("tr").dataset.id;
                const qty = parseFloat(input.value) || 0;
                if (qty <= 0) delete state.cart[id];
                else state.cart[id].qty = qty;
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

    function bindProductCard(card, product) {
        qs(".product-add", card).addEventListener("click", () => {
            const qty = parseFloat(qs(".product-qty", card).value) || 1;
            state.cart[product.id] = {
                id: product.id,
                name: product.name,
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
            <div class="small text-muted">${escapeHtml(p.uom || "")}</div>
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
            if (loadMoreBtn) loadMoreBtn.classList.add("d-none");
        } else if (loadMoreBtn) {
            loadMoreBtn.disabled = true;
            loadMoreBtn.textContent = "Loading...";
        }

        const payload = await rpc("/my/transfers/api/products", {
            term: state.productTerm,
            offset: state.productOffset,
            limit: PAGE_SIZE,
        });
        const products = payload.products || [];
        state.productTotal = payload.total || 0;
        state.productOffset += products.length;

        if (reset && !products.length) {
            productGrid.innerHTML = `<div class="text-muted">No products found</div>`;
            updateProductMeta(false);
            return;
        }

        const html = products.map(productCardHtml).join("");
        if (reset) productGrid.innerHTML = html;
        else productGrid.insertAdjacentHTML("beforeend", html);

        products.forEach((product) => {
            const card = productGrid.querySelector(`.o_portal_product_card[data-id="${product.id}"]`);
            if (card) bindProductCard(card, product);
        });
        updateProductMeta(Boolean(payload.has_more));
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

    qs("#btn_confirm_transfer", root).addEventListener("click", async () => {
        confirmError.classList.add("d-none");
        if (!state.locationSrc || !state.locationDest) {
            showError(confirmError, "Please select source and destination locations.");
            return;
        }
        if (state.locationSrc.id === state.locationDest.id) {
            showError(confirmError, "Source and destination must be different.");
            return;
        }
        const lines = Object.values(state.cart).map((i) => ({ product_id: i.id, qty: i.qty }));
        if (!lines.length) {
            showError(confirmError, "Please add at least one product.");
            return;
        }
        const btn = qs("#btn_confirm_transfer", root);
        btn.disabled = true;
        try {
            const result = await rpc("/my/transfers/api/confirm", {
                location_id: state.locationSrc.id,
                location_dest_id: state.locationDest.id,
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
    const cancelBtn = qs("#btn_cancel_transfer");
    if (!cancelBtn) return;

    cancelBtn.addEventListener("click", async () => {
        if (!window.confirm("Cancel this internal transfer?")) return;
        try {
            const res = await rpc("/my/transfers/api/cancel", {
                picking_id: parseInt(cancelBtn.dataset.pickingId, 10),
            });
            showMessage(msg, res.message || "Cancelled.", "success");
            window.location.reload();
        } catch (e) {
            showMessage(msg, extractError(e), "danger");
        }
    });
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
