(function () {
    'use strict';
    try {
        console.log('[Print Check] Script initialization started');
        console.log('[Print Check] Document readyState:', document.readyState);
        console.log('[Print Check] jQuery available:', typeof window.jQuery !== 'undefined');

        function getEl(selector) {
            return document.querySelector(selector);
        }

        function getVal(selector) {
            var el = getEl(selector);
            return el ? el.value : '';
        }

        function getFieldValue(fieldName, label) {
            var tried = [];
            function trySel(sel, prop) {
                var el = document.querySelector(sel);
                tried.push(sel + (el ? ' [HIT]' : ' [MISS]'));
                if (el) {
                    var v = (prop === 'textContent') ? (el.textContent || '') : (el.value || '');
                    if (v) return v;
                }
                return '';
            }
            // Try common patterns used by OWL/Odoo
            var val =
                trySel('input[name="' + fieldName + '"]') ||
                trySel('input[id*="' + fieldName + '"]') ||
                trySel('.o_field_widget[name="' + fieldName + '"] input') ||
                trySel('.o_field_widget[data-name="' + fieldName + '"] input') ||
                trySel('[data-name="' + fieldName + '"] input') ||
                trySel('[name="' + fieldName + '"] .o_input') ||
                trySel('[data-name="' + fieldName + '"] .o_input', 'textContent');
            console.log('[Print Check] Probe for', label || fieldName, '=>', val ? ('"' + val + '"') : '(empty)', ' | tried:', tried);
            return val;
        }

        function setVal(selector, value) {
            var el = getEl(selector);
            if (el) {
                el.value = value || '';
            }
        }

        function loadTafqeet(callback) {
            if (typeof window.tafqeet === 'function') {
                callback && callback();
                return;
            }
            var existing = document.querySelector('script[data-print-check-taf="1"]');
            if (existing) {
                // wait for it to parse
                return setTimeout(function () { loadTafqeet(callback); }, 100);
            }
            var script = document.createElement('script');
            script.src = '/print_check/static/src/cheque/taf.js';
            script.dataset.printCheckTaf = '1';
            script.onload = function () {
                console.log('[Print Check] taf.js loaded');
                callback && callback();
            };
            script.onerror = function () {
                console.warn('[Print Check] Failed to load taf.js');
            };
            document.head.appendChild(script);
        }

        function toArabicWordsFromAmount(amountStr) {
            try {
                if (typeof window.tafqeet !== 'function') return '';
                if (!amountStr) return '';
                var sanitized = String(amountStr).replace(/[^0-9.]/g, '');
                if (!sanitized) return '';
                var integerPart = sanitized.split('.')[0] || sanitized;
                var num = parseInt(integerPart, 10);
                if (isNaN(num)) return '';
                return window.tafqeet(num) || '';
            } catch (e) {
                console.warn('[Print Check] toArabicWordsFromAmount failed:', e);
                return '';
            }
        }

        function formatCurrencyWords(words) {
            if (!words) return '';
            // strip previous wrappers if any
            var w = String(words).trim();
            w = w.replace(/^فقط\s*/u, '').replace(/\s*ديناراً أردنياً لا غير$/u, '');
            return 'فقط ' + w + ' ديناراً أردنياً لا غير';
        }
        function findPartnerName() {
            // Try select[name=partner_id]
            var sel = document.querySelector('select[name="partner_id"]');
            if (sel && sel.options && sel.selectedIndex >= 0) {
                return (sel.options[sel.selectedIndex].text || '').trim();
            }
            // Try input[name=partner_id]
            var inp = document.querySelector('input[name="partner_id"]');
            if (inp && inp.value) {
                return inp.value.trim();
            }
            // Try OWL many2one structure
            var m2oInput = document.querySelector('.o_field_widget .o_input_dropdown input');
            if (m2oInput && m2oInput.value) {
                return m2oInput.value.trim();
            }
            return '';
        }

        function syncCheckFields() {
            console.log('[Print Check] syncCheckFields called');

            // Partner name
            var partnerName = findPartnerName();
            if (partnerName) {
                setVal('#Payee_name', partnerName);
                console.log('[Print Check] Partner name set:', partnerName);
            } else {
                console.log('[Print Check] Partner name not found yet');
            }

            // Date
            var chequeDate = getFieldValue('cheque_date', 'cheque_date');
            if (chequeDate) {
                setVal('#date1', chequeDate);
                console.log('[Print Check] Date set:', chequeDate);
            } else {
                console.log('[Print Check] Date not found');
            }

            // Amount
            var amountRaw = getFieldValue('cheque_amount', 'cheque_amount');
            if (amountRaw) {
                var amountVal = amountRaw.toString().replace(/,(?=.*\.\d+)/g, '');
                setVal('#chq_amount', amountVal);
                console.log('[Print Check] Amount set:', amountVal);
            } else {
                console.log('[Print Check] Amount not found');
            }

            // Amount in words (using tafqeet if available)
            if ((typeof window.tafqeet === 'function') && (amountRaw)) {
                var words = toArabicWordsFromAmount(amountRaw);
                if (words) {
                    var wrapped = formatCurrencyWords(words);
                    // Update both the input used earlier and the visible labels
                    setVal('#chq_disc', wrapped);
                    var forLbl = getEl('#for_lbl');
                    if (forLbl) {
                        forLbl.innerHTML = wrapped;
                    }
                    var tafkLbl = getEl('#tafk_lbl');
                    if (tafkLbl) {
                        tafkLbl.innerHTML = wrapped;
                    }
                    console.log('[Print Check] Arabic words (tafqeet) set:', wrapped);
                } else {
                    console.log('[Print Check] tafqeet returned empty for amount:', amountRaw);
                }
            } else {
                console.log('[Print Check] tafqeet not loaded or no amount to convert');
            }
        }

        function tryUpdateViewFromInputs() {
            try {
                if (typeof window.upd_fields === 'function') {
                    console.log('[Print Check] Calling window.upd_fields()');
                    window.upd_fields();
                    return true;
                }
            } catch (e) {
                console.warn('[Print Check] window.upd_fields() call failed:', e);
            }
            try {
                var payeeVal = getVal('#Payee_name');
                var payeeLbl = getEl('#Payee_lbl');
                if (payeeLbl && payeeVal) {
                    payeeLbl.innerHTML = payeeVal;
                    console.log('[Print Check] Fallback applied: #Payee_lbl <-', payeeVal);
                }
                var dateVal = getVal('#date1');
                var dateLbl = getEl('#date_lbl');
                if (dateLbl && dateVal) {
                    dateLbl.innerHTML = dateVal;
                    console.log('[Print Check] Fallback applied: #date_lbl <-', dateVal);
                }
                var amountVal = getVal('#chq_amount');
                var amountLbl = getEl('#amount_lbl');
                if (amountLbl && amountVal) {
                    amountLbl.innerHTML = amountVal;
                    console.log('[Print Check] Fallback applied: #amount_lbl <-', amountVal);
                }
                // For the "memo" area on the cheque, use CurNum2Word instead
                var curNum2Word = (function () {
                    var el = document.querySelector('#CurNum2Word');
                    if (el) return (el.value || el.textContent || '').trim();
                    var v = getFieldValue('CurNum2Word', 'CurNum2Word');
                    if (v) return v;
                    var lbl = getEl('#tafk_lbl');
                    if (lbl && lbl.textContent) return lbl.textContent.trim();
                    return getVal('#chq_disc'); // last resort
                })();
                var forLbl = getEl('#for_lbl');
                if (forLbl && curNum2Word) {
                    forLbl.innerHTML = curNum2Word;
                    console.log('[Print Check] Fallback applied: #for_lbl <- (CurNum2Word)', curNum2Word);
                }
                return true;
            } catch (e) {
                console.warn('[Print Check] Fallback label update failed:', e);
                return false;
            }
        }

        function startSync() {
            // Try quickly a few times, then slower
            var attempts = 0;
            var quickTimer = setInterval(function () {
                attempts += 1;
                syncCheckFields();
                tryUpdateViewFromInputs();
                if (attempts >= 5) {
                    clearInterval(quickTimer);
                    // Continue a few more times slower
                    setTimeout(function () { syncCheckFields(); tryUpdateViewFromInputs(); }, 1000);
                    setTimeout(function () { syncCheckFields(); tryUpdateViewFromInputs(); }, 2000);
                    setTimeout(function () { syncCheckFields(); tryUpdateViewFromInputs(); }, 3000);
                }
            }, 300);
            // Ensure taf.js loaded, then re-sync to produce words
            loadTafqeet(function () {
                setTimeout(function () {
                    syncCheckFields();
                    tryUpdateViewFromInputs();
                }, 200);
            });
        }

        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', function () {
                startSync();
            });
        } else {
            startSync();
        }

        // Datepicker (optional) - only if jQuery exists
        (function loadDatepickerIfJQuery() {
            var $ = window.jQuery || window.$;
            if ($) {
                var script = document.createElement('script');
                script.src = '/print_check/static/src/js/javascript999.js';
                script.onload = function () {
                    console.log('[Print Check] Datepicker loaded');
                };
                document.head.appendChild(script);
            }
        })();

        // Attach print handler for .PrintMe button (vanilla JS)
        (function attachPrintHandler() {
            function onClickPrint(e) {
                e.preventDefault();
                try {
                    console.log('[Print Check] Print button clicked - syncing and updating view...');
                    syncCheckFields();
                    tryUpdateViewFromInputs();
                    setTimeout(function () {
                        var allWeb = document.querySelector('#all_web');
                        var printableHtml = allWeb && allWeb.parentElement ? allWeb.parentElement.innerHTML : null;
                        if (!printableHtml) {
                            console.warn('[Print Check] Printable region not found');
                            return;
                        }
                        console.log('[Print Check] Proceeding to print...');
                        var originalHtml = document.body.innerHTML;
                        document.body.innerHTML = printableHtml;
                        window.print();
                        document.body.innerHTML = originalHtml;
                        window.location.reload();
                    }, 120);
                } catch (err) {
                    console.error('[Print Check] Print failed:', err);
                }
            }
            function bind() {
                var buttons = document.querySelectorAll('.PrintMe');
                var boundCount = 0;
                buttons.forEach(function (btn) {
                    if (!btn.dataset.printBound) {
                        btn.addEventListener('click', onClickPrint);
                        btn.dataset.printBound = '1';
                        boundCount += 1;
                    }
                });
                if (boundCount) {
                    console.log('[Print Check] Bound print handlers to', boundCount, 'button(s)');
                }
            }
            if (document.readyState === 'loading') {
                document.addEventListener('DOMContentLoaded', bind);
            } else {
                bind();
            }
            // In case the button is injected later, try a few times
            setTimeout(bind, 500);
            setTimeout(bind, 1500);
            setTimeout(bind, 3000);
        })();

        console.log('[Print Check] Main script execution completed');
    } catch (e) {
        console.error('[Print Check] Fatal error in print_check_sync.js:', e && e.message, e);
    }
})();

