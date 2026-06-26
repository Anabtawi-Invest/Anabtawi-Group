/** @odoo-module **/

import publicWidget from "@web/legacy/js/public/public_widget";

publicWidget.registry.AnabtawiThemeWidget = publicWidget.Widget.extend({
    selector: '.anabtawi-hero, .anabtawi-card',
    start: function () {
        this._super.apply(this, arguments);
        this._initAnimations();
    },
    _initAnimations: function () {
        // Simple subtle animation setups
        console.log("Anabtawi Theme loaded successfully.");
    }
});

// Dynamic Scroll-Driven Video Scrubbing Widget for Odoo
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
        this._tick = this._tick.bind(this);

        this._resizeCanvas();
        this._updateDimensions();
        this._preloadImages();

        window.addEventListener('scroll', this.onScroll, { passive: true });
        window.addEventListener('resize', this.onResize, { passive: true });

        this.active = true;
        this.isTicking = false;
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
            // Path inside Odoo environment
            img.src = `/theme_anabtawi_sweets/static/src/img/frames/frame_${frameStr}.jpg`;

            const promise = new Promise((resolve) => {
                const handleLoaded = () => {
                    if (typeof img.decode === 'function') {
                        img.decode()
                            .then(() => this._onImageLoadedSuccess(resolve))
                            .catch(() => this._onImageLoadedSuccess(resolve));
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

        this.targetFrame = 1 + scrollFraction * (this.totalFrames - 1);

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

