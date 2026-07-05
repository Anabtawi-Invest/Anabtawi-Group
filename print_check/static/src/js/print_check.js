/**
 * Print Check Module - Main JavaScript Controller
 * ================================================
 * 
 * A robust, class-based implementation with:
 * - Proper DOM ready handling with MutationObserver
 * - Event delegation for dynamic elements
 * - State management via PrintCheckApp class
 * - LocalStorage persistence for settings
 * - Real-time preview updates
 * - **RTL isolation enforcement via JavaScript**
 * 
 * RTL PROTECTION:
 * This script includes a forceLTRLayout() method that:
 * 1. Sets inline direction:ltr on key elements
 * 2. Removes any RTL classes Odoo might add
 * 3. Uses MutationObserver to continuously enforce LTR
 * 
 * POSITIONING:
 * Uses margin-based positioning for labels (margin-top, margin-left)
 * instead of transform-based. Margins don't get flipped by RTL direction,
 * making positions stable in Arabic mode.
 * 
 * @version 2.7.0
 * @odoo 19.0
 */

(function (global) {
    'use strict';

    // ===========================================
    // PrintCheckApp - Main Application Class
    // ===========================================

    class PrintCheckApp {
        constructor() {
            // State flags
            this.initialized = false;
            this.rtlObserver = null;
            this.currentContainer = null;  // Track current DOM container
            this.instanceId = null;  // Unique ID for this form instance

            // Load saved settings
            this.settings = this.loadSettings();

            // DOM Elements cache (populated on init)
            this.elements = {};

            // Bind methods to preserve 'this' context
            this.init = this.init.bind(this);
            this.updatePreview = this.updatePreview.bind(this);
            this.print = this.print.bind(this);
            this.forceLTRLayout = this.forceLTRLayout.bind(this);
            this.destroy = this.destroy.bind(this);
        }

        // ===========================================
        // Initialization
        // ===========================================

        /**
         * Initialize the application.
         * Called when the print check form is detected in DOM.
         * 
         * CRITICAL FIX: We use a unique marker on the container to detect
         * when Odoo SPA has replaced the DOM with a new form instance.
         * This ensures we ALWAYS reinitialize for new form instances.
         */
        init() {
            // Check if we're on the print check form
            const container = document.getElementById('printCheckContainer');
            if (!container) {
                console.log('[PrintCheck] Container not found, will retry...');
                return false;
            }

            // Generate a unique ID for this container instance
            // If container already has our marker and matches, skip init
            const instanceId = container.getAttribute('data-pc-instance');

            if (instanceId && instanceId === this.instanceId) {
                console.log('[PrintCheck] Same instance (' + instanceId + '), already initialized');
                return true;
            }

            // New container detected - always reinitialize
            if (this.initialized) {
                console.log('[PrintCheck] New form instance detected, reinitializing...');
                this.destroy();
            }

            // Mark this container with a unique instance ID
            this.instanceId = 'pc_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
            container.setAttribute('data-pc-instance', this.instanceId);

            // Store reference to current container
            this.currentContainer = container;

            console.log('[PrintCheck] ========================================');
            console.log('[PrintCheck] Initializing Print Check Application...');
            console.log('[PrintCheck] Instance ID:', this.instanceId);
            console.log('[PrintCheck] ========================================');

            // CRITICAL: Force LTR layout immediately
            this.forceLTRLayout();

            // Cache DOM element references
            this.cacheElements();

            // Setup event listeners
            this.setupEventListeners();

            // Setup RTL protection observer
            this.setupRTLObserver();

            // Load Odoo field values (with retry for async rendering)
            this.loadOdooFieldsWithRetry();

            // Apply saved settings
            this.applySettings();

            // Initial preview update
            this.updatePreview();

            this.initialized = true;
            console.log('[PrintCheck] ✓ Initialization complete');

            return true;
        }

        /**
         * Load Odoo fields with retry mechanism.
         * Odoo renders fields asynchronously, so we retry a few times.
         * Increased retries and delay to handle slow rendering.
         */
        loadOdooFieldsWithRetry(attempt = 0) {
            const maxAttempts = 10;  // More attempts
            const delay = 300; // ms - longer delay

            // Try to load
            this.loadOdooFields();

            // Check if we got data (at least one field populated)
            const hasData = (this.elements.payeeName?.value && this.elements.payeeName.value.trim()) ||
                (this.elements.date?.value && this.elements.date.value.trim()) ||
                (this.elements.amount?.value && parseFloat(this.elements.amount.value) > 0);

            if (!hasData && attempt < maxAttempts) {
                console.log('[PrintCheck] No data loaded, retrying... (attempt ' + (attempt + 1) + '/' + maxAttempts + ')');
                setTimeout(() => this.loadOdooFieldsWithRetry(attempt + 1), delay);
            } else if (hasData) {
                console.log('[PrintCheck] ✓ Data loaded successfully on attempt ' + (attempt + 1));
                // Update preview with loaded data
                this.updatePreview();
            } else {
                console.warn('[PrintCheck] ✗ Failed to load data after ' + maxAttempts + ' attempts');
                console.warn('[PrintCheck] Check if data bridge elements exist in DOM');
            }
        }

        /**
         * Reset the app state for reinitialization.
         */
        destroy() {
            console.log('[PrintCheck] Destroying previous instance:', this.instanceId);

            if (this.rtlObserver) {
                this.rtlObserver.disconnect();
                this.rtlObserver = null;
            }

            this.elements = {};
            this.currentContainer = null;
            this.instanceId = null;
            this.initialized = false;
        }

        /**
         * Cache DOM element references for faster access
         */
        cacheElements() {
            this.elements = {
                // Main containers
                container: document.getElementById('printCheckContainer'),
                controls: document.getElementById('printCheckControls'),
                preview: document.getElementById('printCheckPreview'),

                // Input fields
                payeeName: document.getElementById('pcPayeeName'),
                date: document.getElementById('pcDate'),
                amount: document.getElementById('pcAmount'),
                tafqeetText: document.getElementById('pcTafqeetText'),
                currency: document.getElementById('pcCurrency'),
                crossing: document.getElementById('pcCrossing'),
                freeText: document.getElementById('pcFreeText'),

                // Position/style sliders
                payeeFontSize: document.getElementById('pcPayeeFontSize'),
                payeeFontWeight: document.getElementById('pcPayeeFontWeight'),
                payeeVertPos: document.getElementById('pcPayeeVertPos'),
                payeeHorzPos: document.getElementById('pcPayeeHorzPos'),
                dateFontSize: document.getElementById('pcDateFontSize'),
                dateFontWeight: document.getElementById('pcDateFontWeight'),
                dateVertPos: document.getElementById('pcDateVertPos'),
                dateHorzPos: document.getElementById('pcDateHorzPos'),
                amountFontSize: document.getElementById('pcAmountFontSize'),
                amountFontWeight: document.getElementById('pcAmountFontWeight'),
                amountVertPos: document.getElementById('pcAmountVertPos'),
                amountHorzPos: document.getElementById('pcAmountHorzPos'),
                tafqeetFontSize: document.getElementById('pcTafqeetFontSize'),
                tafqeetFontWeight: document.getElementById('pcTafqeetFontWeight'),
                tafqeetVertPos: document.getElementById('pcTafqeetVertPos'),
                tafqeetHorzPos: document.getElementById('pcTafqeetHorzPos'),
                crossingFontSize: document.getElementById('pcCrossingFontSize'),
                crossingVertPos: document.getElementById('pcCrossingVertPos'),
                crossingHorzPos: document.getElementById('pcCrossingHorzPos'),
                freeTextFontSize: document.getElementById('pcFreeTextFontSize'),
                freeTextFontWeight: document.getElementById('pcFreeTextFontWeight'),
                freeTextVertPos: document.getElementById('pcFreeTextVertPos'),
                freeTextHorzPos: document.getElementById('pcFreeTextHorzPos'),

                // Preview labels on cheque
                labelDate: document.getElementById('pcLabelDate'),
                labelPayee: document.getElementById('pcLabelPayee'),
                labelAmount: document.getElementById('pcLabelAmount'),
                labelFraction: document.getElementById('pcLabelFraction'),
                labelTafqeet: document.getElementById('pcLabelTafqeet'),
                labelCrossing: document.getElementById('pcLabelCrossing'),
                labelFreeText: document.getElementById('pcLabelFreeText'),

                // Cheque elements
                cheque: document.getElementById('pcCheque'),
                chequeBg: document.getElementById('pcChequeBg'),

                // Print button
                printBtn: document.getElementById('pcPrintBtn')
            };

            console.log('[PrintCheck] Cached', Object.keys(this.elements).length, 'elements');
        }

        // ===========================================
        // RTL ISOLATION - CRITICAL SECTION
        // ===========================================

        /**
         * Force LTR layout on the print check container.
         * This is the PRIMARY defense against RTL flipping.
         * 
         * CRITICAL: The cheque element needs special handling to ensure
         * left/right positioning stays PHYSICAL (left=left) not LOGICAL.
         */
        forceLTRLayout() {
            console.log('[PrintCheck] Enforcing LTR layout...');

            const container = document.getElementById('printCheckContainer');
            if (!container) return;

            // List of elements that MUST stay LTR
            const ltrElements = [
                container,
                document.getElementById('printCheckControls'),
                document.getElementById('printCheckPreview'),
                document.getElementById('pcCheque'),
                document.getElementById('pcPreviewContainer')
            ];

            ltrElements.forEach(el => {
                if (el) {
                    // Force direction via inline style (highest priority)
                    el.style.setProperty('direction', 'ltr', 'important');
                    el.style.setProperty('text-align', 'left', 'important');

                    // Ensure flex doesn't reverse
                    if (el.classList.contains('print-check-container')) {
                        el.style.setProperty('flex-direction', 'row', 'important');
                    }

                    // Set dir attribute
                    el.setAttribute('dir', 'ltr');

                    // Remove any RTL class Odoo might add
                    el.classList.remove('o_rtl', 'rtl');
                }
            });

            // CRITICAL: Force cheque and labels to use physical positioning
            const cheque = document.getElementById('pcCheque');
            if (cheque) {
                cheque.style.setProperty('direction', 'ltr', 'important');
                cheque.style.setProperty('transform', 'none', 'important');

                // Don't set unicode-bidi on cheque - it breaks child elements
            }

            // Also ensure tabs nav stays LTR
            const tabsNav = container.querySelector('.pc-tabs-nav');
            if (tabsNav) {
                tabsNav.style.setProperty('direction', 'ltr', 'important');
                tabsNav.style.setProperty('flex-direction', 'row', 'important');
            }

            // Button groups too
            container.querySelectorAll('.pc-btn-group').forEach(group => {
                group.style.setProperty('direction', 'ltr', 'important');
                group.style.setProperty('flex-direction', 'row', 'important');
            });

            // Controls grid
            container.querySelectorAll('.pc-controls-grid').forEach(grid => {
                grid.style.setProperty('direction', 'ltr', 'important');
            });

            console.log('[PrintCheck] ✓ LTR layout enforced');
        }

        /**
         * Setup MutationObserver to continuously enforce LTR.
         * This catches any dynamic changes Odoo makes after initial load.
         * 
         * NOTE: We use a flag to prevent infinite loops since forceLTRLayout
         * modifies styles which would trigger the observer again.
         */
        setupRTLObserver() {
            if (this.rtlObserver) {
                this.rtlObserver.disconnect();
            }

            const container = this.elements.container;
            if (!container) return;

            // Flag to prevent re-entry
            let isEnforcingLTR = false;

            this.rtlObserver = new MutationObserver((mutations) => {
                // Skip if we're currently enforcing LTR (prevents infinite loop)
                if (isEnforcingLTR) return;

                let needsLTRFix = false;

                for (const mutation of mutations) {
                    // Only care about changes NOT from our own enforcement
                    if (mutation.type === 'attributes') {
                        const target = mutation.target;
                        const attrName = mutation.attributeName;

                        // Check if body got o_rtl class
                        if (target === document.body && attrName === 'class') {
                            if (document.body.classList.contains('o_rtl')) {
                                needsLTRFix = true;
                                break;
                            }
                        }

                        // Check if dir attribute was changed to rtl
                        if (attrName === 'dir' && target.getAttribute('dir') === 'rtl') {
                            needsLTRFix = true;
                            break;
                        }
                    }
                }

                if (needsLTRFix) {
                    console.log('[PrintCheck] RTL mutation detected, re-enforcing LTR...');
                    isEnforcingLTR = true;
                    this.forceLTRLayout();
                    // Reset flag after a short delay
                    setTimeout(() => { isEnforcingLTR = false; }, 100);
                }
            });

            // Only observe body for class changes (o_rtl)
            this.rtlObserver.observe(document.body, {
                attributes: true,
                attributeFilter: ['class']
            });

            // Observe container for dir attribute only (not style)
            this.rtlObserver.observe(container, {
                attributes: true,
                attributeFilter: ['dir'],
                subtree: false  // Don't watch children - too expensive
            });

            console.log('[PrintCheck] RTL observer active');
        }

        // ===========================================
        // Event Listeners
        // ===========================================

        /**
         * Setup all event listeners.
         * Uses event delegation where appropriate for efficiency.
         */
        setupEventListeners() {
            const controls = this.elements.controls;
            if (!controls) return;

            // Event delegation for input/change events
            controls.addEventListener('input', (e) => this.handleInput(e));
            controls.addEventListener('change', (e) => this.handleChange(e));

            // Tab switching with capture phase
            this.setupTabListeners();

            // Honorific buttons
            this.setupHonorificListeners();

            // Option buttons (alignment, surround, etc.)
            this.setupOptionButtonListeners(controls);

            // Print button
            if (this.elements.printBtn) {
                this.elements.printBtn.addEventListener('click', (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    this.print();
                });
            }

            console.log('[PrintCheck] Event listeners attached');
        }

        /**
         * Setup tab navigation listeners
         */
        setupTabListeners() {
            const tabBtns = document.querySelectorAll('.pc-tab-btn');
            tabBtns.forEach(btn => {
                btn.addEventListener('click', (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    const tabId = btn.getAttribute('data-tab');
                    if (tabId) {
                        this.switchTab(tabId);
                    }
                }, true); // Capture phase
            });
        }

        /**
         * Setup honorific button listeners
         */
        setupHonorificListeners() {
            const honorificBtns = document.querySelectorAll('.pc-btn-honorific');
            honorificBtns.forEach(btn => {
                btn.addEventListener('click', (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    e.stopImmediatePropagation();
                    const text = btn.getAttribute('data-text');
                    if (text) {
                        this.insertHonorific(text);
                    }
                }, true);

                // Prevent mousedown interference
                btn.addEventListener('mousedown', (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                }, true);
            });
        }

        /**
         * Setup option button listeners (alignment, surround, numerals, etc.)
         */
        setupOptionButtonListeners(container) {
            // Define button handlers by class
            const buttonHandlers = {
                'pc-btn-align': (btn) => {
                    this.setPayeeAlign(btn.getAttribute('data-align'));
                    this.setActiveButton(btn);
                },
                'pc-btn-surround': (btn) => {
                    this.settings.amountSurround = btn.getAttribute('data-surround');
                    this.setActiveButton(btn);
                    this.updatePreview();
                    this.saveSettings();
                },
                'pc-btn-separator': (btn) => {
                    this.settings.thousandsSeparator = btn.getAttribute('data-separator') === 'on';
                    this.setActiveButton(btn);
                    this.updatePreview();
                    this.saveSettings();
                },
                'pc-btn-numerals': (btn) => {
                    this.settings.arabicNumerals = btn.getAttribute('data-numerals') === 'arabic';
                    this.setActiveButton(btn);
                    this.updatePreview();
                    this.saveSettings();
                },
                'pc-btn-fraction': (btn) => {
                    this.settings.fractionFormat = btn.getAttribute('data-fraction');
                    this.setActiveButton(btn);
                    this.updateTafqeet();
                    this.saveSettings();
                },
                'pc-btn-taf-surround': (btn) => {
                    this.settings.tafqeetSurround = btn.getAttribute('data-surround');
                    this.setActiveButton(btn);
                    this.updateTafqeet();
                    this.saveSettings();
                },
                'pc-btn-taf-align': (btn) => {
                    this.setTafqeetAlign(btn.getAttribute('data-align'));
                    this.setActiveButton(btn);
                }
            };

            // Attach listeners for each button type
            Object.keys(buttonHandlers).forEach(className => {
                container.querySelectorAll('.' + className).forEach(btn => {
                    btn.addEventListener('click', (e) => {
                        e.preventDefault();
                        e.stopPropagation();
                        buttonHandlers[className](btn);
                    }, true);
                });
            });
        }

        /**
         * Handle input events (real-time updates)
         */
        handleInput(e) {
            const target = e.target;
            const id = target.id;

            // Text inputs - update preview
            if (['pcPayeeName', 'pcDate', 'pcAmount', 'pcTafqeetText', 'pcCrossing', 'pcFreeText'].includes(id)) {
                this.updatePreview();
            }

            // Range sliders - immediate visual feedback
            if (target.type === 'range') {
                this.handleSliderInput(target);
                this.saveSettings();
            }
        }

        /**
         * Handle change events (final value, save settings)
         */
        handleChange(e) {
            const target = e.target;

            // Currency change triggers tafqeet update
            if (target.id === 'pcCurrency') {
                this.updateTafqeet();
            }

            // Amount change also updates tafqeet
            if (target.id === 'pcAmount') {
                this.updateTafqeet();
            }

            this.saveSettings();
        }

        /**
         * Handle slider input for immediate visual feedback
         */
        handleSliderInput(slider) {
            const id = slider.id;
            const value = slider.value;

            // Update value display
            const valueDisplay = document.getElementById(id + 'Value');
            if (valueDisplay) {
                const unit = ['FontSize', 'VertPos', 'HorzPos'].some(s => id.includes(s)) ? 'px' : '';
                valueDisplay.textContent = value + unit;
            }

            // Map slider ID to target element and CSS property
            // Use top/left adjustment for positioning with absolute elements
            const sliderMap = {
                pcPayeeFontSize: { el: 'labelPayee', prop: 'fontSize', unit: 'px' },
                pcPayeeFontWeight: { el: 'labelPayee', prop: 'fontWeight', unit: '' },
                pcPayeeVertPos: { el: 'labelPayee', prop: 'top', unit: 'px', isPosition: true },
                pcPayeeHorzPos: { el: 'labelPayee', prop: 'left', unit: 'px', isPosition: true },
                pcDateFontSize: { el: 'labelDate', prop: 'fontSize', unit: 'px' },
                pcDateFontWeight: { el: 'labelDate', prop: 'fontWeight', unit: '' },
                pcDateVertPos: { el: 'labelDate', prop: 'top', unit: 'px', isPosition: true },
                pcDateHorzPos: { el: 'labelDate', prop: 'left', unit: 'px', isPosition: true },
                pcAmountFontSize: { el: ['labelAmount', 'labelFraction'], prop: 'fontSize', unit: 'px' },
                pcAmountFontWeight: { el: ['labelAmount', 'labelFraction'], prop: 'fontWeight', unit: '' },
                pcAmountVertPos: { el: ['labelAmount', 'labelFraction'], prop: 'top', unit: 'px', isPosition: true },
                pcAmountHorzPos: { el: ['labelAmount', 'labelFraction'], prop: 'right', unit: 'px', isPosition: true },  // Amount uses right positioning
                pcTafqeetFontSize: { el: 'labelTafqeet', prop: 'fontSize', unit: 'px' },
                pcTafqeetFontWeight: { el: 'labelTafqeet', prop: 'fontWeight', unit: '' },
                pcTafqeetVertPos: { el: 'labelTafqeet', prop: 'top', unit: 'px', isPosition: true },
                pcTafqeetHorzPos: { el: 'labelTafqeet', prop: 'left', unit: 'px', isPosition: true },
                pcCrossingFontSize: { el: 'labelCrossing', prop: 'fontSize', unit: 'px' },
                pcCrossingVertPos: { el: 'labelCrossing', prop: 'top', unit: 'px', isPosition: true },
                pcCrossingHorzPos: { el: 'labelCrossing', prop: 'left', unit: 'px', isPosition: true },
                pcFreeTextFontSize: { el: 'labelFreeText', prop: 'fontSize', unit: 'px' },
                pcFreeTextFontWeight: { el: 'labelFreeText', prop: 'fontWeight', unit: '' },
                pcFreeTextVertPos: { el: 'labelFreeText', prop: 'top', unit: 'px', isPosition: true },
                pcFreeTextHorzPos: { el: 'labelFreeText', prop: 'left', unit: 'px', isPosition: true }
            };

            const config = sliderMap[id];
            if (!config) return;

            // Apply style to element(s)
            const elements = Array.isArray(config.el) ? config.el : [config.el];
            elements.forEach(elName => {
                const el = this.elements[elName];
                if (el) {
                    if (config.isPosition) {
                        // For position adjustments, modify the base position
                        this.applyPositionAdjustment(el, config.prop, value);
                    } else {
                        el.style[config.prop] = value + config.unit;
                    }
                }
            });
        }

        /**
         * Apply position adjustment from slider.
         * Stores original position and applies offset.
         */
        applyPositionAdjustment(el, prop, adjustment) {
            // Initialize base positions if needed
            if (!el._basePositions) {
                const computed = window.getComputedStyle(el);
                el._basePositions = {
                    top: parseFloat(computed.top) || 0,
                    left: parseFloat(computed.left) || 0,
                    right: parseFloat(computed.right) || 0
                };
            }

            const adjustNum = parseFloat(adjustment) || 0;
            const baseValue = el._basePositions[prop] || 0;
            const finalValue = baseValue + adjustNum;

            el.style.setProperty(prop, finalValue + 'px', 'important');
        }

        // ===========================================
        // Tab Switching
        // ===========================================

        switchTab(tabId) {
            // Hide all panes
            document.querySelectorAll('.pc-tab-pane').forEach(pane => {
                pane.classList.remove('active');
            });

            // Deactivate all tab buttons
            document.querySelectorAll('.pc-tab-btn').forEach(btn => {
                btn.classList.remove('active');
            });

            // Show target pane
            const targetPane = document.getElementById(tabId);
            if (targetPane) {
                targetPane.classList.add('active');
            }

            // Activate target button
            const targetBtn = document.querySelector(`.pc-tab-btn[data-tab="${tabId}"]`);
            if (targetBtn) {
                targetBtn.classList.add('active');
            }

            console.log('[PrintCheck] Switched to tab:', tabId);
        }

        // ===========================================
        // Honorific Insertion
        // ===========================================

        insertHonorific(text) {
            const input = this.elements.payeeName;
            if (!input) {
                console.warn('[PrintCheck] Payee name input not found');
                return;
            }

            const currentValue = input.value || '';
            const isSuffix = text.trim() === 'المحترم' || text.trim() === 'المحترمون';

            let newValue, newPos;

            if (isSuffix) {
                // Suffix honorifics go at the end
                newValue = currentValue.trim() + ' ' + text.trim();
                newPos = newValue.length;
            } else {
                // Prefix honorifics insert at cursor
                const start = input.selectionStart || 0;
                const end = input.selectionEnd || 0;
                newValue = currentValue.substring(0, start) + text + currentValue.substring(end);
                newPos = start + text.length;
            }

            input.value = newValue;

            // Trigger events for Odoo
            input.dispatchEvent(new Event('input', { bubbles: true }));
            input.dispatchEvent(new Event('change', { bubbles: true }));

            // Focus and position cursor
            input.focus();
            if (input.setSelectionRange) {
                input.setSelectionRange(newPos, newPos);
            }

            this.updatePreview();
            console.log('[PrintCheck] Inserted honorific:', text);
        }

        // ===========================================
        // UI Helpers
        // ===========================================

        setActiveButton(button) {
            const group = button.closest('.pc-btn-group');
            if (group) {
                group.querySelectorAll('.pc-btn').forEach(btn => btn.classList.remove('active'));
            }
            button.classList.add('active');
        }

        setPayeeAlign(align) {
            console.log('[PrintCheck] Setting payee align:', align);
            if (this.elements.labelPayee) {
                // Use setProperty with !important to override RTL styles
                this.elements.labelPayee.style.setProperty('text-align', align, 'important');
                console.log('[PrintCheck] Payee label text-align set to:', align);
            }
            this.settings.payeeAlign = align;
            this.saveSettings();
            this.updatePreview();
        }

        setTafqeetAlign(align) {
            console.log('[PrintCheck] Setting tafqeet align:', align);
            if (this.elements.labelTafqeet) {
                // Use setProperty with !important to override RTL styles
                this.elements.labelTafqeet.style.setProperty('text-align', align, 'important');
                console.log('[PrintCheck] Tafqeet label text-align set to:', align);
            }
            this.settings.tafqeetAlign = align;
            this.saveSettings();
            this.updatePreview();
        }

        // ===========================================
        // Preview Updates
        // ===========================================

        updatePreview() {
            this.updateDateLabel();
            this.updatePayeeLabel();
            this.updateAmountLabel();
            this.updateTafqeet();
            this.updateCrossingLabel();
            this.updateFreeTextLabel();
            // Ensure text direction is correct after updates
            this.enforceTextDirection();
        }

        /**
         * Enforce correct text direction on all labels.
         * This prevents RTL from reversing LTR content like dates and numbers.
         */
        enforceTextDirection() {
            // LTR labels (dates, numbers)
            const ltrLabels = [
                this.elements.labelDate,
                this.elements.labelAmount,
                this.elements.labelFraction
            ];

            ltrLabels.forEach(label => {
                if (label) {
                    label.style.setProperty('direction', 'ltr', 'important');
                    label.style.setProperty('unicode-bidi', 'isolate', 'important');
                    label.setAttribute('dir', 'ltr');
                }
            });

            // RTL labels (Arabic text)
            const rtlLabels = [
                this.elements.labelPayee,
                this.elements.labelTafqeet
            ];

            rtlLabels.forEach(label => {
                if (label) {
                    label.style.setProperty('direction', 'rtl', 'important');
                    label.style.setProperty('unicode-bidi', 'isolate', 'important');
                    label.setAttribute('dir', 'rtl');
                }
            });
        }



        updateFreeTextLabel() {
            const input = this.elements.freeText;
            const label = this.elements.labelFreeText;
            if (input && label) {
                label.textContent = input.value || '';
            }
        }

        updateDateLabel() {
            const input = this.elements.date;
            const label = this.elements.labelDate;
            if (input && label) {
                label.textContent = input.value || '';
                // Ensure LTR for date
                label.style.setProperty('direction', 'ltr', 'important');
            }
        }

        updatePayeeLabel() {
            const input = this.elements.payeeName;
            const label = this.elements.labelPayee;
            if (input && label) {
                label.textContent = input.value || '';
            }
        }

        updateCrossingLabel() {
            const input = this.elements.crossing;
            const label = this.elements.labelCrossing;
            if (input && label) {
                label.textContent = input.value || '';
            }
        }

        updateAmountLabel() {
            const input = this.elements.amount;
            const amountLabel = this.elements.labelAmount;
            const fractionLabel = this.elements.labelFraction;

            if (!input || !amountLabel) return;

            const value = parseFloat(input.value) || 0;
            const integerPart = Math.floor(value);

            // Get fraction multiplier from currency
            const currencyEl = this.elements.currency;
            const selectedOption = currencyEl?.selectedOptions[0];
            const fractionMultiplier = parseInt(selectedOption?.getAttribute('data-fr') || '1000', 10);
            const fractionPart = Math.round((value - integerPart) * fractionMultiplier);

            // Format integer with thousands separator
            let integerStr = integerPart.toString();
            if (this.settings.thousandsSeparator) {
                integerStr = integerPart.toLocaleString('en-US');
            }

            // Convert to Arabic numerals if enabled
            if (this.settings.arabicNumerals) {
                integerStr = this.toArabicNumerals(integerStr);
            }

            // Apply surround
            if (this.settings.amountSurround === 'hash') {
                integerStr = '#' + integerStr + '#';
            } else if (this.settings.amountSurround === 'slash') {
                integerStr = '//' + integerStr + '//';
            }

            amountLabel.textContent = integerStr;

            // Update fraction label
            if (fractionLabel) {
                const padLength = fractionMultiplier === 1000 ? 3 : 2;
                let fractionStr = fractionPart.toString().padStart(padLength, '0');
                if (this.settings.arabicNumerals) {
                    fractionStr = this.toArabicNumerals(fractionStr);
                }
                fractionLabel.textContent = fractionStr;
            }
        }

        updateTafqeet() {
            const input = this.elements.amount;
            const textArea = this.elements.tafqeetText;
            const label = this.elements.labelTafqeet;
            const currencyEl = this.elements.currency;

            if (!input) return;

            const value = parseFloat(input.value) || 0;
            if (value <= 0) {
                if (textArea) textArea.value = '';
                if (label) label.textContent = '';
                return;
            }

            // Get currency info
            const selectedOption = currencyEl?.selectedOptions[0];
            const currencyInfo = {
                currency: selectedOption?.getAttribute('data-cur') || 'دينار',
                currencyAccusative: selectedOption?.getAttribute('data-cur2') || 'ديناراً',
                fraction: selectedOption?.getAttribute('data-div') || 'فلس',
                fractionMultiplier: parseInt(selectedOption?.getAttribute('data-fr') || '1000', 10)
            };

            // Generate tafqeet using the global function
            let tafqeetResult = '';
            try {
                if (typeof global.formatChequeAmount === 'function') {
                    tafqeetResult = global.formatChequeAmount(value, currencyInfo, {
                        withCurrency: true,
                        fractionFormat: this.settings.fractionFormat,
                        surround: this.settings.tafqeetSurround
                    });
                } else if (typeof global.tafqeet === 'function') {
                    // Fallback to basic tafqeet
                    const intPart = Math.floor(value);
                    tafqeetResult = global.tafqeet(intPart) + ' ' + currencyInfo.currencyAccusative;

                    // Add surround if needed
                    if (this.settings.tafqeetSurround === 'faqat') {
                        tafqeetResult = 'فقط ' + tafqeetResult + ' لا غير';
                    }
                }
            } catch (e) {
                console.error('[PrintCheck] Tafqeet error:', e);
                tafqeetResult = 'خطأ في التفقيط';
            }

            if (textArea) textArea.value = tafqeetResult;
            if (label) label.textContent = tafqeetResult;
        }

        /**
         * Convert digits to Arabic numerals
         */
        toArabicNumerals(str) {
            const arabicDigits = ['٠', '١', '٢', '٣', '٤', '٥', '٦', '٧', '٨', '٩'];
            return str.toString().replace(/[0-9]/g, d => arabicDigits[parseInt(d, 10)]);
        }

        // ===========================================
        // Odoo Field Loading
        // ===========================================

        loadOdooFields() {
            console.log('[PrintCheck] Loading Odoo field values...');

            /**
             * Extract text content from an Odoo field wrapper element.
             * Odoo 19 renders fields in many ways depending on:
             * - readonly vs editable
             * - field type (char, float, date, etc.)
             * - view mode
             * 
             * This function handles ALL known Odoo rendering patterns.
             */
            const getTextFromOdooField = (wrapperId) => {
                const wrapper = document.getElementById(wrapperId);
                if (!wrapper) {
                    console.log('[PrintCheck] Wrapper not found:', wrapperId);
                    return '';
                }

                // Log HTML for debugging
                console.log('[PrintCheck] ' + wrapperId + ' HTML:', wrapper.innerHTML);

                // Strategy 1: Input element (editable mode)
                const input = wrapper.querySelector('input[type="text"], input:not([type])');
                if (input && input.value) {
                    return input.value.trim();
                }

                // Strategy 2: Span with o_field_* class (readonly mode Odoo 17+)
                const odooFieldSpan = wrapper.querySelector('[class*="o_field"]');
                if (odooFieldSpan) {
                    const text = odooFieldSpan.textContent || '';
                    if (text.trim()) return text.trim();
                }

                // Strategy 3: Any span child (common pattern)
                const spans = wrapper.querySelectorAll('span');
                for (const span of spans) {
                    const text = span.textContent || '';
                    if (text.trim() && text.trim() !== '0.00' && text.trim() !== '0') {
                        return text.trim();
                    }
                }

                // Strategy 4: Div with o_form_widget class
                const formWidget = wrapper.querySelector('.o_form_widget, .o_field_widget');
                if (formWidget) {
                    return formWidget.textContent?.trim() || '';
                }

                // Strategy 5: Check for data-value attribute (some Odoo widgets)
                const dataValue = wrapper.querySelector('[data-value]');
                if (dataValue) {
                    return dataValue.getAttribute('data-value') || '';
                }

                // Strategy 6: Direct text content as last resort
                const text = wrapper.textContent || '';
                // Filter out labels and whitespace
                const cleaned = text.replace(/[\n\t\r]/g, ' ').replace(/\s+/g, ' ').trim();
                return cleaned;
            };

            // Load partner name
            const partnerName = getTextFromOdooField('pcDataPartnerName');
            if (partnerName && this.elements.payeeName) {
                this.elements.payeeName.value = partnerName;
                console.log('[PrintCheck] ✓ Loaded payee:', partnerName);
            } else {
                console.warn('[PrintCheck] ✗ No partner name found');
            }

            // Load date  
            const chequeDate = getTextFromOdooField('pcDataChequeDate');
            if (chequeDate && this.elements.date) {
                this.elements.date.value = chequeDate;
                console.log('[PrintCheck] ✓ Loaded date:', chequeDate);
            } else {
                console.warn('[PrintCheck] ✗ No date found');
            }

            // Load amount - needs special parsing
            const amountText = getTextFromOdooField('pcDataAmount');
            if (amountText && this.elements.amount) {
                // Parse amount - handle various formats
                // Odoo may show: "1,234.567", "1234.567", "١٢٣٤.٥٦٧", etc.
                let cleanAmount = amountText
                    // Remove currency symbols and text
                    .replace(/[^\d.,٠-٩\-]/g, '')
                    // Convert Arabic numerals to Western
                    .replace(/[٠-٩]/g, d => String.fromCharCode('٠'.charCodeAt(0) - d.charCodeAt(0) + 48));

                // Handle European format (comma as decimal)
                // If there's a comma but no dot, and comma has 2-3 digits after, it's decimal
                if (cleanAmount.includes(',') && !cleanAmount.includes('.')) {
                    const parts = cleanAmount.split(',');
                    if (parts.length === 2 && parts[1].length <= 3) {
                        cleanAmount = cleanAmount.replace(',', '.');
                    }
                }

                // Remove thousand separators
                cleanAmount = cleanAmount.replace(/,/g, '');

                const numAmount = parseFloat(cleanAmount) || 0;
                if (numAmount > 0) {
                    this.elements.amount.value = numAmount;
                    console.log('[PrintCheck] ✓ Loaded amount:', numAmount, '(from "' + amountText + '")');
                }
            } else {
                console.warn('[PrintCheck] ✗ No amount found');
            }

            // Load currency code
            const currencyCode = getTextFromOdooField('pcDataCurrency');
            if (currencyCode && this.elements.currency) {
                const options = this.elements.currency.options;
                let found = false;
                const normalizedCode = currencyCode.toUpperCase().trim();

                for (let i = 0; i < options.length; i++) {
                    if (options[i].value.toUpperCase() === normalizedCode) {
                        this.elements.currency.selectedIndex = i;
                        console.log('[PrintCheck] ✓ Loaded currency:', normalizedCode);
                        found = true;
                        break;
                    }
                }

                if (!found) {
                    console.warn('[PrintCheck] ✗ Currency not in dropdown:', currencyCode);
                }
            }

            // Trigger preview update after loading
            console.log('[PrintCheck] Triggering preview update...');
            setTimeout(() => this.updatePreview(), 150);
        }

        // ===========================================
        // Settings Persistence
        // ===========================================

        loadSettings() {
            const defaults = {
                amountSurround: 'none',
                thousandsSeparator: true,
                arabicNumerals: false,
                fractionFormat: 'normal',
                tafqeetSurround: 'faqat',
                payeeAlign: 'right',
                tafqeetAlign: 'right',
                payeeFontSize: 16,
                payeeFontWeight: 400,
                payeeVertPos: 0,
                payeeHorzPos: 0,
                dateFontSize: 14,
                dateFontWeight: 400,
                dateVertPos: 0,
                dateHorzPos: 0,
                amountFontSize: 16,
                amountFontWeight: 400,
                amountVertPos: 0,
                amountHorzPos: 0,
                tafqeetFontSize: 14,
                tafqeetFontWeight: 400,
                tafqeetVertPos: 0,
                tafqeetHorzPos: 0,
                crossingFontSize: 12,
                crossingVertPos: 0,
                crossingHorzPos: 0,
                crossingText: 'يصرف للمستفيد الأول',

                freeText: '',
                freeTextFontSize: 11,
                freeTextFontWeight: 400,
                freeTextVertPos: 0,
                freeTextHorzPos: 0
            };


            try {
                const saved = localStorage.getItem('printCheckSettings_v2');
                if (saved) {
                    return { ...defaults, ...JSON.parse(saved) };
                }
            } catch (e) {
                console.warn('[PrintCheck] Failed to load settings:', e);
            }

            return defaults;
        }

        saveSettings() {
            // Collect slider values
            const sliderKeys = [
                'payeeFontSize', 'payeeFontWeight', 'payeeVertPos', 'payeeHorzPos',
                'dateFontSize', 'dateFontWeight', 'dateVertPos', 'dateHorzPos',
                'amountFontSize', 'amountFontWeight', 'amountVertPos', 'amountHorzPos',
                'tafqeetFontSize', 'tafqeetFontWeight', 'tafqeetVertPos', 'tafqeetHorzPos',
                'crossingFontSize', 'crossingVertPos', 'crossingHorzPos',
                'freeTextFontSize', 'freeTextFontWeight', 'freeTextVertPos', 'freeTextHorzPos'
            ];

            sliderKeys.forEach(key => {
                const el = this.elements[key];
                if (el) {
                    this.settings[key] = parseInt(el.value, 10);
                }
            });

            // Save crossing text
            if (this.elements.crossing) {
                this.settings.crossingText = this.elements.crossing.value;
            }
            if (this.elements.freeText) {
                this.settings.freeText = this.elements.freeText.value;
            }

            try {
                localStorage.setItem('printCheckSettings_v2', JSON.stringify(this.settings));
            } catch (e) {
                console.warn('[PrintCheck] Failed to save settings:', e);
            }
        }

        applySettings() {
            // Apply slider values
            Object.keys(this.settings).forEach(key => {
                const el = this.elements[key];
                if (el?.type === 'range') {
                    el.value = this.settings[key];
                    this.handleSliderInput(el);
                }
            });

            // Apply crossing text
            if (this.settings.crossingText && this.elements.crossing) {
                this.elements.crossing.value = this.settings.crossingText;
                this.updateCrossingLabel();
            }
            if (this.settings.freeText && this.elements.freeText) {
                this.elements.freeText.value = this.settings.freeText;
                this.updateFreeTextLabel();
            }

            // Apply button states
            const buttonMappings = [
                { class: 'pc-btn-surround', attr: 'data-surround', value: this.settings.amountSurround },
                { class: 'pc-btn-separator', attr: 'data-separator', value: this.settings.thousandsSeparator ? 'on' : 'off' },
                { class: 'pc-btn-numerals', attr: 'data-numerals', value: this.settings.arabicNumerals ? 'arabic' : 'english' },
                { class: 'pc-btn-fraction', attr: 'data-fraction', value: this.settings.fractionFormat },
                { class: 'pc-btn-taf-surround', attr: 'data-surround', value: this.settings.tafqeetSurround },
                { class: 'pc-btn-taf-align', attr: 'data-align', value: this.settings.tafqeetAlign }
            ];

            buttonMappings.forEach(({ class: className, attr, value }) => {
                document.querySelectorAll('.' + className).forEach(btn => {
                    btn.classList.toggle('active', btn.getAttribute(attr) === value);
                });
            });

            // Apply text alignments (use setProperty with !important for RTL override)
            if (this.elements.labelPayee) {
                this.elements.labelPayee.style.setProperty('text-align', this.settings.payeeAlign, 'important');
            }
            if (this.elements.labelTafqeet) {
                this.elements.labelTafqeet.style.setProperty('text-align', this.settings.tafqeetAlign, 'important');
            }

            // Also update the active button for alignment groups
            document.querySelectorAll('.pc-btn-align').forEach(btn => {
                btn.classList.toggle('active', btn.getAttribute('data-align') === this.settings.payeeAlign);
            });

            console.log('[PrintCheck] Settings applied');
        }

        // ===========================================
        // Print Functionality
        // ===========================================

        print() {
            console.log('[PrintCheck] Initiating print...');

            const cheque = this.elements.cheque;
            if (!cheque) {
                alert('خطأ: لم يتم العثور على الشيك / Error: Cheque not found');
                return;
            }

            // Clone the cheque element
            const clone = cheque.cloneNode(true);

            // Hide background image for printing (printing on real cheque paper)
            const bgImg = clone.querySelector('.pc-cheque-bg');
            if (bgImg) {
                bgImg.style.display = 'none';
            }

            // CRITICAL: Copy ALL computed styles including positions
            this.copyAllStylesToClone(cheque, clone);

            // Build print content with styles
            const printStyles = `
                <style>
                    @page { 
                        size: 16.6cm 8.2cm; 
                        margin: 0; 
                    }
                    * { 
                        box-sizing: border-box; 
                        margin: 0; 
                        padding: 0; 
                    }
                    html, body { 
                        width: 16.6cm;
                        height: 8.2cm;
                        margin: 0;
                        padding: 0;
                        direction: ltr !important;
                        background: white;
                    }
                    .pc-cheque {
                        width: 16.6cm;
                        height: 8.2cm;
                        position: relative;
                        border: none !important;
                    }
                    .pc-label {
                        position: absolute;
                        color: #000;
                        font-family: Arial, sans-serif;
                        white-space: pre-wrap;
                    }
                </style>
            `;

            const printContent = printStyles + clone.outerHTML;

            // Store original body content
            const originalContent = document.body.innerHTML;

            // Replace body with print content
            document.body.innerHTML = printContent;

            // Print
            window.print();

            // Restore original content and reload to re-initialize
            document.body.innerHTML = originalContent;

            // Reload page to reinitialize the component
            setTimeout(() => window.location.reload(), 100);

            console.log('[PrintCheck] Print completed');
        }

        /**
         * Copy ALL computed styles from source labels to cloned labels.
         * This ensures the print output matches exactly what's shown in preview.
         */
        copyAllStylesToClone(source, target) {
            const labels = source.querySelectorAll('.pc-label');
            const cloneLabels = target.querySelectorAll('.pc-label');

            labels.forEach((label, i) => {
                const cloneLabel = cloneLabels[i];
                if (!cloneLabel) return;

                const computed = window.getComputedStyle(label);

                // Copy ALL critical positioning and styling properties
                const props = [
                    // Position
                    'position', 'top', 'left', 'right', 'bottom',
                    // Dimensions
                    'width', 'height', 'maxWidth',
                    // Typography
                    'fontSize', 'fontWeight', 'fontFamily', 'lineHeight',
                    'textAlign', 'direction', 'whiteSpace',
                    // Spacing
                    'marginTop', 'marginLeft', 'marginRight', 'marginBottom',
                    'paddingTop', 'paddingLeft', 'paddingRight', 'paddingBottom',
                    // Transform (for diagonal crossing)
                    'transform', 'transformOrigin',
                    // Other
                    'color', 'visibility', 'display'
                ];

                props.forEach(prop => {
                    const value = computed.getPropertyValue(prop.replace(/([A-Z])/g, '-$1').toLowerCase());
                    if (value) {
                        cloneLabel.style.setProperty(prop.replace(/([A-Z])/g, '-$1').toLowerCase(), value);
                    }
                });

                // Also copy any inline styles that were set
                if (label.style.cssText) {
                    // Merge inline styles (they take priority)
                    const inlineStyles = label.style.cssText;
                    cloneLabel.style.cssText = cloneLabel.style.cssText + '; ' + inlineStyles;
                }
            });

            console.log('[PrintCheck] Copied styles for', labels.length, 'labels');
        }
    }

    // ===========================================
    // Application Bootstrap
    // ===========================================

    const app = new PrintCheckApp();

    /**
     * Safe initialization with error handling
     */
    function safeInit() {
        try {
            const result = app.init();
            if (result) {
                console.log('[PrintCheck] ✓ Initialization successful');
            }
            return result;
        } catch (e) {
            console.error('[PrintCheck] Init error:', e);
            return false;
        }
    }

    /**
     * Setup MutationObserver to detect when form is loaded
     */
    function setupFormObserver() {
        if (!document.body) {
            setTimeout(setupFormObserver, 100);
            return;
        }

        console.log('[PrintCheck] Setting up form observer...');

        // Track the last known container to detect changes
        let lastContainerId = null;

        const observer = new MutationObserver((mutations) => {
            const container = document.getElementById('printCheckContainer');
            if (container) {
                const currentId = container.getAttribute('data-pc-instance');

                // If container exists but has no instance ID or different ID, init
                if (!currentId || currentId !== lastContainerId) {
                    console.log('[PrintCheck] Container change detected via MutationObserver');
                    console.log('[PrintCheck] Previous:', lastContainerId, 'Current:', currentId);
                    lastContainerId = currentId;
                    // Small delay to ensure all children are rendered
                    setTimeout(safeInit, 150);
                }
            }
        });

        observer.observe(document.body, {
            childList: true,
            subtree: true
        });

        // Don't disconnect the observer - we need it running to detect navigation
        // Just log that it's active
        console.log('[PrintCheck] Form observer active (persistent)');
    }

    /**
     * Aggressive polling for container (backup for MutationObserver)
     * This runs continuously to catch any missed navigation events.
     */
    function pollForContainer() {
        let lastInstanceId = null;

        const poll = () => {
            const container = document.getElementById('printCheckContainer');

            if (container) {
                const currentId = container.getAttribute('data-pc-instance');

                // Initialize if no instance ID yet (new container)
                if (!currentId) {
                    console.log('[PrintCheck] New container found via polling');
                    safeInit();
                    lastInstanceId = container.getAttribute('data-pc-instance');
                } else if (currentId !== lastInstanceId) {
                    // Instance changed
                    console.log('[PrintCheck] Instance change detected via polling');
                    lastInstanceId = currentId;
                }
            }

            // Continue polling every 500ms
            setTimeout(poll, 500);
        };

        // Start polling after a short delay
        setTimeout(poll, 300);
    }

    // Initialize based on document state
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => {
            console.log('[PrintCheck] DOMContentLoaded fired');
            safeInit();
            setupFormObserver();
            pollForContainer();
        });
    } else {
        console.log('[PrintCheck] Document already ready');
        safeInit();
        setupFormObserver();
        pollForContainer();
    }

    // Export to global scope
    global.PrintCheckApp = app;
    global.initPrintCheck = () => {
        console.log('[PrintCheck] Manual init triggered');
        app.initialized = false;
        return safeInit();
    };

    console.log('[PrintCheck] Script loaded successfully');

})(typeof window !== 'undefined' ? window : this);
