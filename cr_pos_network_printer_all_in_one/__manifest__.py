# -*- coding: utf-8 -*-
# Part of Creyox Technologies
{
    'name': 'All in One Odoo PoS Printing Solution | Odoo POS Network Printer & USB Printing Solution',
    "author": "Creyox Technologies",
    "website": "https://www.creyox.com",
    "support": "support@creyox.com",
    'category': 'Point of Sale',
    'summary': """
        All in One Odoo PoS Printing Solution enables fast, reliable receipt and kitchen 
        order printing using Network and USB printers. It supports multiple PoS sessions, 
        locations, and printers while delivering real-time, delay-free printing. 
        
        Powered by a lightweight Print Engine Client, this solution works without installing 
        printer drivers and supports all ESC/POS thermal printers. Easy to set up and highly 
        dependable, it reduces manual effort, improves operational efficiency, and ensures 
        consistent printing accuracy for businesses of all sizes using Odoo Point of Sale.
    """,
    "license": "OPL-1",
    'version': '19.0.0.7',
    'description': """
        <h1>All in One Odoo PoS Printing Solution – Network & USB Printers</h1>
        <p>The All in One Odoo PoS Printing Solution ensures smooth, reliable, and real-time receipt and order printing for Odoo Point of Sale. It supports both Network and USB printers, delivering consistent and accurate printing across multiple PoS sessions and business locations.</p>
        
        <h2>Key Features</h2>
        <ul>
            <li>Supports Network and USB PoS printers</li>
            <li>Real-time receipt and kitchen order printing</li>
            <li>No printer driver installation required</li>
            <li>Compatible with all ESC/POS thermal printers</li>
            <li>Lightweight Print Engine Client for Windows, Linux, and Raspberry Pi</li>
            <li>Supports multiple printers and client engines</li>
            <li>Works across multiple PoS sessions and locations</li>
        </ul>
        
        <h2>Benefits</h2>
        <ul>
            <li>Eliminates printing delays in Odoo PoS</li>
            <li>Reduces manual setup and maintenance effort</li>
            <li>Ensures consistent and accurate print output</li>
            <li>Improves operational efficiency at checkout and kitchen</li>
            <li>Ideal for retail, restaurants, and multi-store businesses</li>
        </ul>
        
        <h2>Why Choose This Odoo PoS Printing Solution?</h2>
        <p>This solution offers a dependable and scalable PoS printing system for Odoo users. With driver-free setup, broad printer compatibility, and real-time performance, it simplifies receipt and kitchen printing while supporting business growth.</p>
        
        <h2>Related Apps</h2>
        <ul>
            <li><a href="https://apps.odoo.com/apps/modules/18.0/cr_pos_network_printer_res">POS Network Printer</a></li>
            <li><a href="https://apps.odoo.com/apps/modules/18.0/cr_pos_network_printer">Odoo POS Network Printer</a></li>
            <li><a href="https://apps.odoo.com/apps/modules/18.0/cr_pos_product_addons_group">POS Product Addon Group</a></li>
            <li><a href="https://apps.odoo.com/apps/modules/18.0/cr_sylq_pos_payment">POS Sylq Payment Terminal Integration</a></li>
            <li><a href="https://apps.odoo.com/apps/modules/18.0/cr_fiserv_pos_payment">POS Fiserv Payment Integration</a></li>
            <li><a href="https://apps.odoo.com/apps/modules/18.0/cr_pos_receipt_design_kit">POS Receipt</a></li>
        </ul>
        
        <p>For custom Odoo integrations and CRM enhancements, visit <a href="https://creyox.com">Creyox Technologies</a></p>
        <p>Watch the youtube video, visit <a href="https://www.youtube.com/@CreyoxTechnologies">Creyox Technologies YouTube Videos</a></p>
        <p>Read our blog post, visit <a href="https://www.creyox.com/blog">Creyox Technologies Blogs</a></p>
    """,
    'depends': ['pos_restaurant', 'cr_all_in_one_direct_print'],
    'data': [ 
        'views/res_config_settings_views.xml',
        'views/pos_printer_views.xml',
        'views/print_job_views.xml',
        'views/printer_printer_views.xml',
        'views/pos_config_views.xml',
    ],
    'installable': True,
    'auto_install': False,
    'application': True,
    'assets': {
        'point_of_sale._assets_pos': [
            'cr_pos_network_printer_all_in_one/static/src/**/*',
        ],
    },
    "images": ["static/description/banner.png"],
    "price": 105,
    "currency": "USD",
}
