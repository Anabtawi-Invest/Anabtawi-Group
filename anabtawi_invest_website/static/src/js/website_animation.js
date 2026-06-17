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

// 3. Dynamic Scroll-Driven Video Scrubbing Widget
publicWidget.registry.AnabtawiScrollVideo = publicWidget.Widget.extend({
    selector: '.scroll-video-section',

    start: function () {
        this._super.apply(this, arguments);
        this.canvas = this.el.querySelector('#scrub-canvas');
        if (!this.canvas) return;

        this.ctx = this.canvas.getContext('2d');
        this.loader = this.el.querySelector('.video-loader');
        this.progressBar = this.el.querySelector('.progress-bar');

        this.totalFrames = 120;
        this.images = [];
        this.loadedCount = 0;
        this.targetFrame = 1;
        this.currentFrame = 1;
        this.lastDrawnFrame = 0;
        this.lerpFactor = 0.08;

        // Cache positions to avoid layout thrashing/reflow on scroll
        this.elementTopDoc = 0;
        this.elementHeight = 0;

        this.onScroll = this._onScroll.bind(this);
        this.onResize = this._onResize.bind(this);
        this._tick = this._tick.bind(this); // Bind once here to prevent GC overhead

        this._resizeCanvas();
        this._updateDimensions();
        this._preloadImages();

        window.addEventListener('scroll', this.onScroll, { passive: true });
        window.addEventListener('resize', this.onResize, { passive: true });

        this.active = true;
        this.isTicking = false; // Flag to check if RAF is running
    },

    _resizeCanvas: function () {
        const dpr = window.devicePixelRatio || 1;
        this.canvas.width = this.canvas.clientWidth * dpr;
        this.canvas.height = this.canvas.clientHeight * dpr;
    },

    _updateDimensions: function () {
        const rect = this.el.getBoundingClientRect();
        this.elementTopDoc = rect.top + window.scrollY;
        this.elementHeight = rect.height;
    },

    _preloadImages: function () {
        const promises = [];
        for (let i = 1; i <= this.totalFrames; i++) {
            const img = new Image();
            const frameStr = String(i).padStart(4, '0');
            img.src = `/anabtawi_invest_website/static/src/img/frames/frame_${frameStr}.jpg`;

            const promise = new Promise((resolve) => {
                const handleLoaded = () => {
                    // Modern performance: Decode image asynchronously to cache in GPU
                    if (typeof img.decode === 'function') {
                        img.decode()
                            .then(() => this._onImageLoadedSuccess(resolve))
                            .catch(() => this._onImageLoadedSuccess(resolve)); // fallback if decode fails
                    } else {
                        this._onImageLoadedSuccess(resolve);
                    }
                };

                img.addEventListener('load', handleLoaded);
                img.addEventListener('error', () => this._onImageLoadedSuccess(resolve));
            });
            promises.push(promise);
            this.images.push(img);
        }
    },

    _onImageLoadedSuccess: function (resolve) {
        this.loadedCount++;
        if (this.progressBar) {
            const percent = Math.round((this.loadedCount / this.totalFrames) * 100);
            this.progressBar.style.width = `${percent}%`;
        }
        if (this.loadedCount === this.totalFrames) {
            if (this.loader) {
                this.loader.classList.add('loaded');
            }
            this._drawFrame(1);
            // Draw correct initial frame based on starting scroll position
            this._onScroll();
        }
        resolve();
    },

    _onResize: function () {
        this._resizeCanvas();
        this._updateDimensions();
        this._drawFrame(Math.round(this.currentFrame));
    },

    _onScroll: function () {
        if (this.loadedCount < this.totalFrames) return;

        const scrollY = window.scrollY;
        const viewportHeight = window.innerHeight;
        const totalScrollable = this.elementHeight - viewportHeight;

        if (totalScrollable <= 0) return;

        const scrolled = scrollY - this.elementTopDoc;
        const scrollFraction = Math.min(1.0, Math.max(0.0, scrolled / totalScrollable));

        // Target frame goes from 1 to 120
        this.targetFrame = 1 + scrollFraction * (this.totalFrames - 1);

        // Run animation tick loop only when actively scrolling/interpolating
        if (!this.isTicking) {
            this.isTicking = true;
            window.requestAnimationFrame(this._tick);
        }
    },

    _tick: function () {
        if (!this.active) {
            this.isTicking = false;
            return;
        }

        const diff = this.targetFrame - this.currentFrame;
        if (Math.abs(diff) > 0.001) {
            this.currentFrame += diff * this.lerpFactor;
            const frameToDraw = Math.round(this.currentFrame);
            if (frameToDraw !== this.lastDrawnFrame) {
                this._drawFrame(frameToDraw);
                this.lastDrawnFrame = frameToDraw;
            }
            window.requestAnimationFrame(this._tick);
        } else {
            // Snap to final target and stop requesting frames to save CPU
            this.currentFrame = this.targetFrame;
            const frameToDraw = Math.round(this.currentFrame);
            if (frameToDraw !== this.lastDrawnFrame) {
                this._drawFrame(frameToDraw);
                this.lastDrawnFrame = frameToDraw;
            }
            this.isTicking = false;
        }
    },

    _drawFrame: function (frameIndex) {
        const img = this.images[frameIndex - 1];
        if (!img || !img.complete) return;

        const ctx = this.ctx;
        const canvas = this.canvas;

        // Optimization: clearRect is removed because cover logic fully overwrites the canvas.
        // This avoids redundant compositing writes, speeding up execution.

        // Aspect ratio cover logic
        const imgWidth = img.width;
        const imgHeight = img.height;
        const canvasWidth = canvas.width;
        const canvasHeight = canvas.height;

        const imgRatio = imgWidth / imgHeight;
        const canvasRatio = canvasWidth / canvasHeight;

        let drawWidth, drawHeight, offsetX, offsetY;

        if (canvasRatio > imgRatio) {
            drawWidth = canvasWidth;
            drawHeight = canvasWidth / imgRatio;
            offsetX = 0;
            offsetY = (canvasHeight - drawHeight) / 2;
        } else {
            drawWidth = canvasHeight * imgRatio;
            drawHeight = canvasHeight;
            offsetX = (canvasWidth - drawWidth) / 2;
            offsetY = 0;
        }

        ctx.drawImage(img, offsetX, offsetY, drawWidth, drawHeight);
    },

    destroy: function () {
        this.active = false;
        window.removeEventListener('scroll', this.onScroll);
        window.removeEventListener('resize', this.onResize);
        this._super.apply(this, arguments);
    }
});

export default {
    AnabtawiScrollAnimation: publicWidget.registry.AnabtawiScrollAnimation,
    AnabtawiKunafaStretch: publicWidget.registry.AnabtawiKunafaStretch,
    AnabtawiScrollVideo: publicWidget.registry.AnabtawiScrollVideo
};
