/** @odoo-module **/

/* ==========================================================================
   Anabtawi Invest Public Widgets & Scroll Animations
   ========================================================================== */

import publicWidget from "@web/legacy/js/public/public_widget";

// 1. Scroll Fade-In Animations Widget
publicWidget.registry.AnabtawiScrollAnimation = publicWidget.Widget.extend({
    selector: '.scroll-fade-in',

    start: function () {
        this._super.apply(this, arguments);
        if ('IntersectionObserver' in window) {
            const observerOptions = {
                root: null,
                rootMargin: '0px 0px -8% 0px',
                threshold: 0.05
            };
            this.observer = new IntersectionObserver((entries) => {
                entries.forEach(entry => {
                    if (entry.isIntersecting) {
                        entry.target.classList.add('visible');
                        this.observer.unobserve(entry.target);
                    }
                });
            }, observerOptions);
            this.observer.observe(this.el);
        } else {
            this.el.classList.add('visible');
        }
    },

    destroy: function () {
        if (this.observer) {
            this.observer.disconnect();
        }
        this._super.apply(this, arguments);
    }
});

// 2. Interactive Kunafa Stretch Background Widget
publicWidget.registry.AnabtawiKunafaStretch = publicWidget.Widget.extend({
    selector: '.kunafa-stretch-bg',

    start: function () {
        this._super.apply(this, arguments);
        this.cheese = this.el.querySelector('.kunafa-cheese');
        this.bottom = this.el.querySelector('.kunafa-bottom');
        
        if (!this.cheese || !this.bottom) return;

        // Measure initial unscaled dimensions
        this.initialCheeseHeight = this.cheese.offsetHeight || 120;
        this.ticking = false;

        this.onScroll = this._onScroll.bind(this);
        this.onResize = this._onResize.bind(this);

        window.addEventListener('scroll', this.onScroll, { passive: true });
        window.addEventListener('resize', this.onResize, { passive: true });

        // Trigger initial alignment
        this._onScroll();
    },

    _onResize: function () {
        // Temporarily clear transforms to measure natural height
        const tempCheeseTransform = this.cheese.style.transform;
        this.cheese.style.transform = 'none';
        this.initialCheeseHeight = this.cheese.offsetHeight || 120;
        this.cheese.style.transform = tempCheeseTransform;
    },

    _onScroll: function () {
        if (!this.ticking) {
            window.requestAnimationFrame(() => {
                const scrollY = window.scrollY;
                const docHeight = document.documentElement.scrollHeight || document.body.scrollHeight;
                const viewportHeight = window.innerHeight;
                const maxScroll = Math.max(1, docHeight - viewportHeight);
                
                // Linear scroll fraction [0.0 - 1.0]
                const scrollFraction = Math.min(1.0, Math.max(0.0, scrollY / maxScroll));

                // scaleY stretches from 1.0 to 2.2 times
                const scaleY = 1.0 + (scrollFraction * 1.2);
                // scaleX thins out from 1.0 down to 0.85 (Volume preservation / organic stretch)
                const scaleX = 1.0 - (scrollFraction * 0.15);

                // Apply stretch transforms
                this.cheese.style.transform = `scaleY(${scaleY}) scaleX(${scaleX})`;
                
                // Calculate tray translation to match stretched cheese bottom
                const deltaY = this.initialCheeseHeight * (scaleY - 1);
                this.bottom.style.transform = `translateY(${deltaY}px)`;

                this.ticking = false;
            });
            this.ticking = true;
        }
    },

    destroy: function () {
        window.removeEventListener('scroll', this.onScroll);
        window.removeEventListener('resize', this.onResize);
        this._super.apply(this, arguments);
    }
});

export default {
    AnabtawiScrollAnimation: publicWidget.registry.AnabtawiScrollAnimation,
    AnabtawiKunafaStretch: publicWidget.registry.AnabtawiKunafaStretch
};
