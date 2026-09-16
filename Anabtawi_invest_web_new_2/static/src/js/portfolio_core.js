/** @odoo-module **/

/** Shared by the Odoo Interaction and the generated standalone preview. */
export function mountInvestPortfolio(root) {
    const header = document.querySelector('.invest-header-shell') || root.querySelector('.invest-header-shell');
    const langBtn = document.getElementById('lang-toggle-btn') || root.querySelector('#lang-toggle-btn');
    const brandContainers = document.querySelectorAll('.invest-brand, .invest-orbit-core, .invest-footer-top a');
    const contactForm = document.getElementById('invest-contact-form') || root.querySelector('#invest-contact-form');
    const successAlert = document.getElementById('form-success-alert') || root.querySelector('#form-success-alert');

    // 1. Sticky Header Scroll detection
    const handleScroll = () => {
        if (header) {
            if (window.scrollY > 40) {
                header.classList.add('scrolled');
            } else {
                header.classList.remove('scrolled');
            }
        }
    };
    window.addEventListener('scroll', handleScroll, { passive: true });

    // 2. 3D Logo Tilt Physics
    const handleMouseMove = (e) => {
        const container = e.currentTarget;
        const img = container.querySelector('img') || container.querySelector('.invest-brand-visual');
        if (!img) return;

        const rect = container.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const y = e.clientY - rect.top;
        const xPercent = (x / rect.width) - 0.5;
        const yPercent = (y / rect.height) - 0.5;
        
        const rotY = xPercent * 28;
        const rotX = -yPercent * 22;
        img.style.transform = `perspective(700px) rotateX(${rotX}deg) rotateY(${rotY}deg) scale(1.08) translateZ(12px)`;
    };

    const handleMouseLeave = (e) => {
        const container = e.currentTarget;
        const img = container.querySelector('img') || container.querySelector('.invest-brand-visual');
        if (img) {
            img.style.transform = 'perspective(700px) rotateX(0deg) rotateY(0deg) scale(1) translateZ(0)';
        }
    };

    brandContainers.forEach(container => {
        container.addEventListener('mousemove', handleMouseMove);
        container.addEventListener('mouseleave', handleMouseLeave);
    });

    // 3. Contact Form Submission
    const handleFormSubmit = (e) => {
        e.preventDefault();
        if (successAlert) {
            successAlert.style.display = 'block';
            contactForm.reset();
            setTimeout(() => {
                successAlert.style.display = 'none';
            }, 6000);
        }
    };
    contactForm?.addEventListener('submit', handleFormSubmit);

    // 4. Mode Toggles (Flow vs Grid)
    const flowBtn = document.getElementById('btn-mode-flow');
    const gridBtn = document.getElementById('btn-mode-grid');
    const flowView = document.getElementById('portfolio-flow-view');
    const gridView = document.getElementById('portfolio-grid-view');

    const handleFlowClick = () => {
        flowBtn?.classList.add('active');
        gridBtn?.classList.remove('active');
        if (flowView) flowView.style.display = 'block';
        if (gridView) gridView.style.display = 'none';
    };
    const handleGridClick = () => {
        gridBtn?.classList.add('active');
        flowBtn?.classList.remove('active');
        if (flowView) flowView.style.display = 'none';
        if (gridView) gridView.style.display = 'block';
    };

    flowBtn?.addEventListener('click', handleFlowClick);
    gridBtn?.addEventListener('click', handleGridClick);

    // Return cleanup
    return () => {
        window.removeEventListener('scroll', handleScroll);
        brandContainers.forEach(container => {
            container.removeEventListener('mousemove', handleMouseMove);
            container.removeEventListener('mouseleave', handleMouseLeave);
        });
        contactForm?.removeEventListener('submit', handleFormSubmit);
        flowBtn?.removeEventListener('click', handleFlowClick);
        gridBtn?.removeEventListener('click', handleGridClick);
    };
}
