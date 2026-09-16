/** @odoo-module **/
import { Interaction } from '@web/public/interaction';
import { registry } from '@web/core/registry';
import { mountInvestPortfolio } from './portfolio_core';

class InvestPortfolio extends Interaction {
    static selector = '.invest-page';
    start() {
        this.cleanupPortfolio = mountInvestPortfolio(this.el);
    }
    destroy() {
        this.cleanupPortfolio?.();
    }
}
registry.category('public.interactions').add('anabtawi_invest_website.portfolio', InvestPortfolio);
