/** @odoo-module **/
import { Interaction } from '@web/public/interaction';
import { registry } from '@web/core/registry';
import { mountInvestPortfolio } from './portfolio_core';

class InvestPortfolio extends Interaction {
    static selector = '.invest-page';
    start() {
        if (!this.el.dataset.investMounted) {
            this.el.dataset.investMounted = 'true';
            this.cleanupPortfolio = mountInvestPortfolio(this.el);
        }
    }
    destroy() {
        this.cleanupPortfolio?.();
        delete this.el.dataset.investMounted;
    }
}

try {
    registry.category('public.interactions').add('Anabtawi_invest_web_new_2.portfolio', InvestPortfolio);
} catch (e) {
    // Graceful fallback if registry key is not available
}

// Resilient fallback initialization on DOM ready
if (typeof window !== 'undefined') {
    const autoInit = () => {
        const root = document.querySelector('.invest-page');
        if (root && !root.dataset.investMounted) {
            root.dataset.investMounted = 'true';
            mountInvestPortfolio(root);
        }
    };
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', autoInit);
    } else {
        autoInit();
    }
}
