/** @odoo-module **/

/**
 * Anabtawi Invest - Integrated Bilingual System, Marquee Ticker, 3D Tilt, and Smooth Scroll
 */

const I18N = {
  en: {
    page_title: "Anabtawi Invest | Diversified Companies, Unified Vision",
    brand_name: "ANABTAWI INVEST",
    brand_sub: "EST. 1954",
    closing_brand: "ANABTAWI INVEST",
    footer_copy: "© Anabtawi Invest. All rights reserved.",
    skip_to_content: "Skip to content",
    nav_about: "About Us",
    nav_companies: "Our Companies",
    nav_sectors: "Sectors",
    nav_contact: "Contact Us",
    nav_cta: "Explore Portfolio",
    hero_h1: "Deep Roots.<br/><em>Renewed Horizons.</em>",
    hero_desc: "From the authenticity of fine food to future-facing enterprise.<br/>A diversified business group uniting heritage, excellence, and forward growth.",
    hero_cta1: "Explore Companies",
    hero_cta2: "Our Legacy Story",
    hero_foot: "Diversified ventures, unified identity.",
    hero_scroll_more: "Discover More",
    hq_location: "Amman, Jordan",
    about_eyebrow: "THE GROUP / ABOUT US",
    about_h2: "Diversified Ventures.<br/><em>Unified Vision.</em>",
    about_p1: "Anabtawi Invest brings together a forward-thinking family of companies spanning fine foods, trade, agriculture, and digital business solutions. Each company carries its own distinctive legacy and focused expertise, united by shared values of authenticity and ambition.",
    about_p2: "From handcrafted Arabic sweets, premium honey, and artisanal dairy to modern livestock farming, purebred Arabian horses, and enterprise ERP solutions, our portfolio reflects diversity, resilience, and sustainable growth across generations.",
    about_link: "Explore Our Full Story",
    fact_companies: "Companies in Our Portfolio",
    fact_sectors: "Core Business Sectors",
    fact_vision_title: "One Vision",
    fact_vision_desc: "Uniting our expertise and ambition",
    portfolio_eyebrow: "PORTFOLIO / SUBSIDIARIES",
    portfolio_h2: "A World of <em>Expertise.</em>",
    portfolio_desc: "Distinct brand identities, synergistic value.<br/>Discover the companies that define our group.",
    mode_flow: "Continuous Flow",
    mode_grid: "Grid View",
    filter_all: "All Companies",
    filter_food: "Food & Trade",
    filter_agri: "Agri & Nature",
    filter_tech: "Business Solutions",
    sectors_eyebrow: "OUR SECTORS / BUSINESS DOMAINS",
    sectors_h2: "Multiple Domains.<br/><em>Broader Horizons.</em>",
    sectors_desc: "From fertile land to advanced industry, from handcrafted food to digital technology.<br/>Cross-disciplinary expertise creating enduring value.",
    sector1_title: "Food & Commerce",
    sector1_desc: "Traditional and luxury confectionery, cheese manufacturing, food processing, and wholesale trade.",
    sector2_title: "Agriculture & Nature",
    sector2_desc: "Pure apiculture and honey production, sustainable livestock farming, and purebred Arabian horses.",
    sector3_title: "Tech & Business Solutions",
    sector3_desc: "Enterprise Resource Planning (ERP), CRM systems, and integrated supply chain management solutions.",
    explore_companies: "Explore Companies",
    contact_eyebrow: "CONNECT / CONTACT US",
    contact_h2: "Let's Build the Future Together.",
    contact_lead: "We welcome strategic partnerships, investment inquiries, and institutional collaborations across our diverse portfolio.",
    card_hq_title: "Headquarters",
    card_hq_val: "Amman, Jordan · King Abdullah II St., Commercial District",
    card_phone_title: "Direct Line",
    card_email_title: "General Inquiries",
    card_hours_title: "Working Hours",
    card_hours_val: "Sunday – Thursday: 8:30 AM – 5:00 PM",
    form_title: "Send Us an Inquiry",
    form_lbl_name: "Full Name *",
    form_lbl_email: "Email Address *",
    form_lbl_phone: "Phone Number",
    form_lbl_sector: "Sector of Interest",
    form_lbl_msg: "Your Message *",
    opt_general: "General Inquiries",
    opt_food: "Food & Confectionery",
    opt_agri: "Agriculture & Livestock",
    opt_tech: "Enterprise & Technology",
    opt_partner: "Investment & Partnerships",
    form_btn: "Send Message",
    form_success: "✓ Thank you. Your message has been received. Our team will reach out promptly.",
    closing_h2: "Proud of Our Heritage.<br/><em>Looking Far Beyond.</em>",
    closing_btn: "Explore the Group",
    card_about_btn: "About Company",
    card_visit_site: "Visit Website"
  },
  ar: {
    page_title: "عنبتاوي للإستثمار | شركات متنوعة، رؤية واحدة",
    brand_name: "عنبتاوي للإستثمار",
    brand_sub: "تأسست 1954",
    closing_brand: "عنبتاوي للإستثمار",
    footer_copy: "© عنبتاوي للإستثمار. جميع الحقوق محفوظة.",
    skip_to_content: "انتقل إلى المحتوى",
    nav_about: "عن المجموعة",
    nav_companies: "شركاتنا",
    nav_sectors: "قطاعاتنا",
    nav_contact: "تواصل معنا",
    nav_cta: "اكتشف المجموعة",
    hero_h1: "جذور راسخة.<br/><em>آفاق متجددة.</em>",
    hero_desc: "من أصالة الغذاء إلى حلول المستقبل.<br/>مجموعة أعمال تجمع الخبرة والتنوع، وتفتح آفاقًا جديدة.",
    hero_cta1: "اكتشف شركاتنا",
    hero_cta2: "حكاية المجموعة",
    hero_foot: "أعمال متنوعة، وهوية واحدة.",
    hero_scroll_more: "اكتشف المزيد",
    hq_location: "عمّان، الأردن",
    about_eyebrow: "المجموعة / من نحن",
    about_h2: "تنوّع في الأعمال.<br/><em>أصالة في الرؤية.</em>",
    about_p1: "تجمع عنبتاوي للإستثمار محفظة من الشركات في الصناعات الغذائية والتجارة والزراعة وحلول الأعمال. لكل شركة تخصصها وهويتها، وللمجموعة حكاية مشتركة من الخبرة والطموح.",
    about_p2: "من الحلويات العربية والعسل والأجبان، إلى الثروة الحيوانية والخيول العربية وأنظمة إدارة المؤسسات؛ تنوّع يعكس اتساع أعمال المجموعة.",
    about_link: "تعرّف على عالم عنبتاوي",
    fact_companies: "شركات في محفظتنا",
    fact_sectors: "مجالات أعمال رئيسية",
    fact_vision_title: "رؤية واحدة",
    fact_vision_desc: "تجمع خبراتنا وطموحاتنا",
    portfolio_eyebrow: "محفظة المجموعة / شركاتنا",
    portfolio_h2: "عالم من <em>الخبرات.</em>",
    portfolio_desc: "هويات مختلفة، وقيمة تتكامل.<br/>اكتشف الشركات التي تشكّل مجموعتنا.",
    mode_flow: "المسار المتحرك",
    mode_grid: "شبكة العرض",
    filter_all: "جميع الشركات",
    filter_food: "الغذاء والتجارة",
    filter_agri: "الزراعة والطبيعة",
    filter_tech: "حلول الأعمال",
    sectors_eyebrow: "قطاعاتنا / مجالات أعمالنا",
    sectors_h2: "مجالات متعددة.<br/><em>فرص أوسع.</em>",
    sectors_desc: "من الأرض إلى الصناعة، ومن المنتج إلى التقنية.<br/>خبرات تتقاطع لتشكّل صورة المجموعة.",
    sector1_title: "الغذاء والتجارة",
    sector1_desc: "حلويات وأجبان وتصنيع غذائي، وتجارة واستيراد المواد الغذائية.",
    sector2_title: "الزراعة والطبيعة",
    sector2_desc: "العسل وتربية النحل، والثروة الحيوانية، والخيول العربية الأصيلة.",
    sector3_title: "تقنية وحلول أعمال",
    sector3_desc: "أنظمة إدارة المؤسسات وعلاقات العملاء وسلاسل الإمداد.",
    explore_companies: "استكشف الشركات",
    contact_eyebrow: "تواصل معنا / قنوات الاتصال",
    contact_h2: "لنصنع معاً مستقبلاً واعداً.",
    contact_lead: "نرحّب بالشراكات الاستراتيجية واستفسارات الاستثمار والتعاون المؤسسي عبر كافة قطاعات مجموعتنا.",
    card_hq_title: "المقر الرئيسي",
    card_hq_val: "عمّان، المملكة الأردنية الهاشمية · شارع الملك عبدالله الثاني، المنطقة التجارية",
    card_phone_title: "الهاتف المباشر",
    card_email_title: "البريد الإلكتروني",
    card_hours_title: "أوقات العمل",
    card_hours_val: "الأحد – الخميس: 8:30 صباحاً – 5:00 مساءً",
    form_title: "أرسل استفسارك إلينا",
    form_lbl_name: "الاسم الكامل *",
    form_lbl_email: "البريد الإلكتروني *",
    form_lbl_phone: "رقم الهاتف",
    form_lbl_sector: "القطاع المهتم به",
    form_lbl_msg: "رسالتك *",
    opt_general: "استفسار عام",
    opt_food: "الصناعات الغذائية والتجارة",
    opt_agri: "الزراعة والإنتاج الحيواني",
    opt_tech: "حلول الأعمال والتقنية",
    opt_partner: "الاستثمار والشراكات",
    form_btn: "إرسال الرسالة",
    form_success: "✓ شكراً لتواصلك معنا. تم استلام رسالتك بنجاح وسيتواصل معك فريقنا قريباً.",
    closing_h2: "نعتزّ بجذورنا.<br/><em>ونتطلّع إلى ما هو أبعد.</em>",
    closing_btn: "اكتشف المجموعة",
    card_about_btn: "عن الشركة",
    card_visit_site: "زيارة الموقع"
  }
};

export function mountInvestPortfolio(root) {
    const header = document.querySelector('.invest-header-shell') || root.querySelector('.invest-header-shell');
    const brandContainers = document.querySelectorAll('.invest-brand, .invest-orbit-core, .invest-footer-top a');
    const contactForm = document.getElementById('invest-contact-form') || root.querySelector('#invest-contact-form');
    const successAlert = document.getElementById('form-success-alert') || root.querySelector('#form-success-alert');

    // 1. Initial State: Strict hiding of form success message
    if (successAlert) {
        successAlert.classList.remove('is-visible');
        successAlert.style.setProperty('display', 'none', 'important');
    }

    // 2. Sticky Header Scroll detection
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

    // 3. Smooth Gliding Motion for all Section Links
    const handleSmoothScroll = (e) => {
        const anchor = e.target.closest('a[href*="#"]');
        if (!anchor) return;
        const href = anchor.getAttribute('href');
        if (!href) return;
        const hashIdx = href.indexOf('#');
        if (hashIdx === -1) return;
        const hash = href.substring(hashIdx);
        if (hash === '#' || hash === '#!') return;

        const path = href.substring(0, hashIdx);
        const currentPath = window.location.pathname;
        if (!path || path === currentPath || path === '/invest' || currentPath.endsWith(path)) {
            const target = document.querySelector(hash);
            if (target) {
                e.preventDefault();
                target.scrollIntoView({
                    behavior: 'smooth',
                    block: 'start'
                });
                try {
                    window.history.pushState(null, null, hash);
                } catch(err) {}
            }
        }
    };
    document.addEventListener('click', handleSmoothScroll);

    // 4. 3D Logo Tilt Physics
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

    // 5. Contact Form Submission (Only reveals alert on submit)
    const handleFormSubmit = (e) => {
        e.preventDefault();
        if (successAlert) {
            successAlert.classList.add('is-visible');
            successAlert.style.setProperty('display', 'block', 'important');
            contactForm.reset();
            setTimeout(() => {
                successAlert.classList.remove('is-visible');
                successAlert.style.setProperty('display', 'none', 'important');
            }, 6000);
        }
    };
    contactForm?.addEventListener('submit', handleFormSubmit);

    // 6. Mode Toggles (Flow vs Grid)
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

    // 7. Category Filtering
    const filterBtns = document.querySelectorAll('.invest-filters [data-filter]');
    filterBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            const sector = btn.getAttribute('data-filter');
            filterBtns.forEach(b => b.setAttribute('aria-pressed', 'false'));
            btn.setAttribute('aria-pressed', 'true');

            const allCards = document.querySelectorAll('.invest-company');
            allCards.forEach(card => {
                const match = sector === 'all' || card.getAttribute('data-sector') === sector;
                card.style.display = match ? '' : 'none';
            });

            if (sector !== 'all' && gridBtn) {
                handleGridClick();
            }
        });
    });

    const sectorLinks = document.querySelectorAll('[data-sector-link]');
    sectorLinks.forEach(link => {
        link.addEventListener('click', (e) => {
            const sector = link.getAttribute('data-sector-link');
            const targetBtn = document.querySelector(`.invest-filters [data-filter="${sector}"]`);
            if (targetBtn) {
                targetBtn.click();
            }
        });
    });

    // 8. Bilingual Language Switching
    let currentLang = 'en';

    const setLanguage = (lang) => {
        currentLang = lang;
        document.documentElement.setAttribute('lang', lang);
        document.documentElement.setAttribute('dir', lang === 'ar' ? 'rtl' : 'ltr');

        // Update Brand Names
        const brandName = I18N[lang].brand_name;
        const heroBrand = document.getElementById('hero-brand-name');
        if (heroBrand) heroBrand.textContent = brandName;
        const heroSub = document.getElementById('hero-brand-sub');
        if (heroSub) heroSub.textContent = I18N[lang].brand_sub;
        const closingBrand = document.getElementById('closing-brand-name');
        if (closingBrand) closingBrand.textContent = brandName;
        const footerCopy = document.getElementById('footer-copy-text');
        if (footerCopy) footerCopy.textContent = I18N[lang].footer_copy;

        // Toggle button text (shows alternate language)
        const langBtnText = document.getElementById('lang-btn-text');
        if (langBtnText) {
            langBtnText.textContent = lang === 'en' ? 'العربية' : 'English';
        }

        // Update data-i18n elements
        document.querySelectorAll('[data-i18n]').forEach(el => {
            const key = el.getAttribute('data-i18n');
            if (I18N[lang] && I18N[lang][key]) {
                el.innerHTML = I18N[lang][key];
            }
        });

        // Update card attributes if any
        document.querySelectorAll('[data-i18n-ar]').forEach(el => {
            const val = el.getAttribute(lang === 'ar' ? 'data-i18n-ar' : 'data-i18n-en');
            if (val) el.textContent = val;
        });

        // Direction arrows
        document.querySelectorAll('.arrow-dir').forEach(el => {
            el.textContent = lang === 'ar' ? '↙' : '↘';
        });
        document.querySelectorAll('.arrow-sub').forEach(el => {
            el.textContent = lang === 'ar' ? '←' : '→';
        });

        try {
            localStorage.setItem('anabtawi_invest_lang', lang);
        } catch(err) {}
    };

    // Determine initial language
    let initialLang = 'en';
    try {
        const saved = localStorage.getItem('anabtawi_invest_lang');
        if (saved === 'ar' || saved === 'en') {
            initialLang = saved;
        } else if (document.documentElement.lang.startsWith('ar') || document.documentElement.dir === 'rtl') {
            initialLang = 'ar';
        }
    } catch(err) {}
    setLanguage(initialLang);

    const langToggleBtn = document.getElementById('lang-toggle-btn');
    const handleLangToggle = () => {
        const nextLang = currentLang === 'en' ? 'ar' : 'en';
        setLanguage(nextLang);
    };
    langToggleBtn?.addEventListener('click', handleLangToggle);

    // Return cleanup
    return () => {
        window.removeEventListener('scroll', handleScroll);
        document.removeEventListener('click', handleSmoothScroll);
        brandContainers.forEach(container => {
            container.removeEventListener('mousemove', handleMouseMove);
            container.removeEventListener('mouseleave', handleMouseLeave);
        });
        contactForm?.removeEventListener('submit', handleFormSubmit);
        flowBtn?.removeEventListener('click', handleFlowClick);
        gridBtn?.removeEventListener('click', handleGridClick);
        langToggleBtn?.removeEventListener('click', handleLangToggle);
    };
}
