/** @odoo-module **/

(function () {
    'use strict';

    var currentBasePrice = 0.0;
    var currentMultiplier = 1.0;
    var currentVariantId = null;
    var currentTemplateId = null;
    var currentProductName = '';

    function formatPrice(val) {
        return parseFloat(val || 0).toFixed(3);
    }

    function generateSizePills(productName, basePrice, currency) {
        var container = document.getElementById('anabtawi_modal_sizes_container');
        if (!container) return;
        container.innerHTML = '';

        var sizes = [];
        var nameLower = (productName || '').toLowerCase();

        // Check if name has a package weight like 250غم, 500غم, 800غم, etc.
        var matchGrams = productName.match(/(\d+)\s*(?:غم|g|gm)/i);
        var matchKg = productName.match(/(\d+(?:\.\d+)?)\s*(?:كغ|kg)/i);

        if (matchKg && parseFloat(matchKg[1]) === 1) {
            // Standard 1kg sweet (like Kunafah, Baklava 1kg)
            sizes = [
                { label: '0.5 كغ', multiplier: 0.5, isDefault: false },
                { label: '1.0 كغ (الأساسي)', multiplier: 1.0, isDefault: true },
                { label: '1.5 كغ', multiplier: 1.5, isDefault: false },
                { label: '2.0 كغ (عائلي)', multiplier: 2.0, isDefault: false }
            ];
        } else if (matchGrams) {
            var g = parseInt(matchGrams[1], 10);
            sizes = [
                { label: 'علبة واحدة (' + g + 'غم)', multiplier: 1.0, isDefault: true },
                { label: 'علبتين (' + (g * 2) + 'غم)', multiplier: 2.0, isDefault: false },
                { label: '3 علب (توفير عائلي)', multiplier: 3.0, isDefault: false }
            ];
        } else if (nameLower.includes('كيك') || nameLower.includes('cake') || nameLower.includes('تارت')) {
            sizes = [
                { label: 'صغير / Small (6-8 أشخاص)', multiplier: 1.0, isDefault: true },
                { label: 'وسط / Medium (10-12 شخص)', multiplier: 1.4, isDefault: false },
                { label: 'كبير / Large (14-16 شخص)', multiplier: 1.8, isDefault: false }
            ];
        } else {
            // General premium sweet sizes
            sizes = [
                { label: 'حجم عادي (قياسي)', multiplier: 1.0, isDefault: true },
                { label: 'حجم عائلي (+توفير)', multiplier: 1.5, isDefault: false },
                { label: 'حجم ضيافة فاخر', multiplier: 2.0, isDefault: false }
            ];
        }

        currentMultiplier = 1.0;

        sizes.forEach(function (s) {
            var btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'anabtawi-size-pill' + (s.isDefault ? ' active' : '');
            
            var calculatedPrice = formatPrice(basePrice * s.multiplier);
            btn.textContent = s.label + ' (' + calculatedPrice + ' ' + currency + ')';
            btn.setAttribute('data-multiplier', s.multiplier);

            btn.addEventListener('click', function () {
                var pills = container.querySelectorAll('.anabtawi-size-pill');
                pills.forEach(function (p) { p.classList.remove('active'); });
                btn.classList.add('active');

                currentMultiplier = s.multiplier;
                updateDisplayedPrice();
            });

            container.appendChild(btn);
        });
    }

    function updateDisplayedPrice() {
        var priceEl = document.getElementById('anabtawi_modal_price');
        if (priceEl) {
            var unitP = currentBasePrice * currentMultiplier;
            priceEl.textContent = formatPrice(unitP);
        }
    }

    function openModal() {
        var modal = document.getElementById('anabtawiQuickViewModal');
        if (!modal) return;
        modal.style.display = 'flex';
        // force reflow for smooth animation
        void modal.offsetWidth;
        modal.classList.add('active');
        document.body.style.overflow = 'hidden';
    }

    function closeModal() {
        var modal = document.getElementById('anabtawiQuickViewModal');
        if (!modal) return;
        modal.classList.remove('active');
        setTimeout(function () {
            modal.style.display = 'none';
            document.body.style.overflow = '';
        }, 250);
    }

    function initQuickView() {
        if (window.__anabtawiQuickViewInitialized) {
            return;
        }
        window.__anabtawiQuickViewInitialized = true;

        var modal = document.getElementById('anabtawiQuickViewModal');
        var modalImg = document.getElementById('anabtawi_modal_img');
        var modalTitle = document.getElementById('anabtawi_modal_title');
        var modalCateg = document.getElementById('anabtawi_modal_categ');
        var modalCurr = document.getElementById('anabtawi_modal_currency');
        var modalDesc = document.getElementById('anabtawi_modal_desc');
        var modalQty = document.getElementById('anabtawi_modal_qty');
        var modalFeedback = document.getElementById('anabtawi_modal_feedback');
        var closeBtn = document.getElementById('anabtawi_modal_close_btn');
        var qtyMinus = document.getElementById('anabtawi_qty_minus');
        var qtyPlus = document.getElementById('anabtawi_qty_plus');
        var addBtn = document.getElementById('anabtawi_modal_add_btn');
        var addText = document.getElementById('anabtawi_modal_add_text');

        // Close handlers
        if (closeBtn) {
            closeBtn.onclick = function (e) {
                if (e) e.preventDefault();
                closeModal();
            };
        }

        if (modal) {
            modal.onclick = function (e) {
                if (e.target === modal) {
                    closeModal();
                }
            };
        }

        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape' && modal && modal.classList.contains('active')) {
                closeModal();
            }
        });

        // Stepper Quantity handlers - strictly 1 by 1 (1, 2, 3, 4, 5...)
        if (qtyMinus && modalQty) {
            qtyMinus.onclick = function (e) {
                if (e) {
                    e.preventDefault();
                    e.stopPropagation();
                }
                var q = parseInt(modalQty.value, 10) || 1;
                if (q > 1) {
                    modalQty.value = q - 1;
                } else {
                    modalQty.value = 1;
                }
            };
        }
        if (qtyPlus && modalQty) {
            qtyPlus.onclick = function (e) {
                if (e) {
                    e.preventDefault();
                    e.stopPropagation();
                }
                var q = parseInt(modalQty.value, 10) || 1;
                modalQty.value = q + 1;
            };
        }

        // Add to Cart handler via Odoo 19 /shop/cart/add jsonrpc
        if (addBtn) {
            addBtn.onclick = function (e) {
                if (e) {
                    e.preventDefault();
                    e.stopPropagation();
                }
                if (!currentVariantId || !currentTemplateId) return;

                var qty = parseInt(modalQty ? modalQty.value : '1', 10) || 1;
                var originalText = addText ? addText.textContent : 'أضف إلى السلة';

                if (addText) {
                    addText.innerHTML = '<i class="fa fa-spinner fa-spin me-1"></i> جاري الإضافة...';
                }

                var payload = {
                    jsonrpc: "2.0",
                    method: "call",
                    params: {
                        product_template_id: parseInt(currentTemplateId, 10),
                        product_id: parseInt(currentVariantId, 10),
                        quantity: qty
                    }
                };

                fetch('/shop/cart/add', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-Requested-With': 'XMLHttpRequest'
                    },
                    body: JSON.stringify(payload)
                })
                .then(function (res) {
                    return res.json();
                })
                .then(function (data) {
                    if (data.error) {
                        console.error('Cart add error:', data.error);
                        if (addText) addText.innerHTML = '<i class="fa fa-exclamation-circle me-1"></i> تعذر الإضافة!';
                        setTimeout(function () {
                            if (addText) addText.textContent = originalText;
                        }, 2200);
                        return;
                    }

                    var result = data.result || {};
                    var newCartQty = result.cart_quantity;

                    // Update button state to success
                    if (addText) {
                        addText.innerHTML = '<i class="fa fa-check-circle me-1"></i> تمت الإضافة بنجاح!';
                    }
                    if (modalFeedback) {
                        modalFeedback.innerHTML = '<i class="fa fa-check-circle me-1"></i> تمت إضافة <b>' + (currentProductName || 'الصنف') + '</b> إلى سلة المشتريات! <a href="/shop/cart" class="text-white text-decoration-underline fw-bold ms-2">عرض السلة وإتمام الطلب ←</a>';
                        modalFeedback.style.display = 'block';
                    }

                    // Update cart badge in navbar
                    var badges = document.querySelectorAll('.my_cart_quantity, .o_wsale_my_cart .badge');
                    badges.forEach(function (b) {
                        b.textContent = newCartQty !== undefined ? newCartQty.toString() : (parseInt(b.textContent || '0', 10) + qty).toString();
                        b.classList.remove('d-none');
                    });

                    setTimeout(function () {
                        if (addText) addText.textContent = originalText;
                    }, 2800);
                })
                .catch(function (err) {
                    console.error('Network error on add to cart:', err);
                    if (addText) addText.textContent = originalText;
                });
            };
        }

        // Global delegate for clicking the Quick View eye button
        document.addEventListener('click', function (e) {
            var btn = e.target.closest('.anabtawi-btn-quickview');
            if (!btn) return;

            e.preventDefault();
            e.stopPropagation();

            var templateId = btn.getAttribute('data-template-id');
            var variantId = btn.getAttribute('data-product-id');
            var name = btn.getAttribute('data-product-name') || 'صنف فاخر';
            var price = parseFloat(btn.getAttribute('data-product-price') || '0');
            var currency = btn.getAttribute('data-product-currency') || 'JOD';
            var img = btn.getAttribute('data-product-img') || '';
            var categ = btn.getAttribute('data-product-categ') || 'حلويات فاخرة';
            var desc = btn.getAttribute('data-product-desc') || 'أشهى أصناف الحلويات الفاخرة المحضرة يومياً بأجود المكونات الطبيعية والسمن البلدي الأصيل.';

            currentTemplateId = templateId;
            currentVariantId = variantId;
            currentProductName = name;
            currentBasePrice = price;
            currentMultiplier = 1.0;

            if (modalImg) modalImg.src = img;
            if (modalTitle) modalTitle.textContent = name;
            if (modalCateg) modalCateg.textContent = categ;
            if (modalCurr) modalCurr.textContent = currency;
            if (modalDesc) modalDesc.textContent = desc;
            if (modalQty) modalQty.value = '1';
            if (modalFeedback) modalFeedback.style.display = 'none';

            updateDisplayedPrice();
            generateSizePills(name, currentBasePrice, currency);
            openModal();
        }, true);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initQuickView);
    } else {
        initQuickView();
    }
})();
