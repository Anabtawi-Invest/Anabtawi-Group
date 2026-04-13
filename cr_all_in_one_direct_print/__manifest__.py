# -*- coding: utf-8 -*-
# Part of Creyox Technologies
{
    "name": "All In One Direct Print | Advanced Direct Print Pro | Odoo Print Engine Seamless Odoo Printer Integration & Auto-Print",
    "author": "Creyox Technologies",
    "website": "https://www.creyox.com",
    "support": "support@creyox.com",
    "category": "Extra Tools",
    "summary": """
        Seamless capability to print Any Reports directly from Odoo to local or network printers. 
        Includes a robust Print Job Manager, automatic printer discovery & secure local print engine.
    """,
    "license": "OPL-1",
    "version": "19.0.0.2",
    "description": """
        <h1>Advanced Direct Print Pro for Odoo</h1>
        
        <p>
        The <b>#1 Direct Printing Solution for Odoo</b>. Instantly print Reports directly from Odoo to any local or network printer—no PDF downloads, no browser dialogs, no friction.
        </p>
        
        <p>
        Designed for high-volume businesses that demand speed, reliability, and full control over their printing workflow.
        </p>
        
        <h2>Overview</h2>
        <p>
        <b>Advanced Direct Print Pro</b> is a powerful Odoo printer integration module that connects your Odoo system to local and network printers via a secure Print Engine Client.  
        It completely bypasses the browser print dialog and sends print jobs straight to the OS printer spooler.
        </p>
        
        <h2>Key Features</h2>
        <ul>
          <li><i class="fa fa-check"></i> <b>Seamless Direct Printing</b> – Print instantly without downloading or opening PDFs</li>
          <li><i class="fa fa-check"></i> <b>Universal Printer Support</b> – USB, Network (LAN/WiFi), and Bluetooth printers</li>
          <li><i class="fa fa-check"></i> <b>Auto-Print Rules</b> – Automatically print specific reports to predefined printers</li>
          <li><i class="fa fa-check"></i> <b>Smart Printer Discovery</b> – Sync all local printers into Odoo with one click</li>
          <li><i class="fa fa-check"></i> <b>Advanced Print Job Queue</b> – Track, retry, and manage every print job</li> 
          <li><i class="fa fa-check"></i> <b>Secure Local Communication</b> – Token-based authentication using <code>Print Key</code></li>
        </ul>
        
        <h2>Detailed Features</h2>
        
        <p><b>Auto-Print per Report</b><br/>
        Configure Any reports to auto-print immediately upon generation no user interaction required.
        </p>
        
        <p><b>Printer Sync & Discovery</b><br/>
        Use the built-in “Discover Printers” button to automatically fetch all printers available on the local machine and sync them with Odoo.
        </p>
        
        <p><b>Print Job Monitoring</b><br/>
        Dedicated menu to view print job status (Draft, Printing, Done, Error), preview generated images, and reprint failed jobs instantly.
        </p>
        
        <p><b>Test Printer Utility</b><br/>
        Verify printer connectivity using a built-in graphical test receipt.
        </p>
        
        
        <h3>FAQs</h3>
        
        <p><b>Q1: Does this work on Odoo.sh or Cloud hosting?</b><br/>
        Yes. The module is specifically designed to work with cloud-hosted Odoo instances by securely connecting to a local Print Engine Client.
        </p>
        
        <p><b>Q2: Can I auto-print without user interaction?</b><br/>
        Absolutely. You can configure reports to auto-print immediately upon generation to a predefined printer.
        </p>
        
        <p><b>Q3: Which printers are supported?</b><br/>
        All printers supported by the operating system, including USB, network, Bluetooth, receipt printers, and barcode/label printers.
        </p>
        
        <p><b>Q4: Is the connection secure?</b><br/>
        Yes. Communication between Odoo and the Print Engine is protected using token-based authentication.
        </p>
        
        <h2>Why Choose Us?</h2>
        <ul>
          <li><i class="fa fa-check"></i> Built for high-volume, mission-critical printing</li>
          <li><i class="fa fa-check"></i> Enterprise-grade architecture with real job tracking</li>
          <li><i class="fa fa-check"></i> Clean, well-structured code following Odoo standards</li>
          <li><i class="fa fa-check"></i> Actively maintained with long-term support</li>
          <li><i class="fa fa-check"></i> Trusted by production Odoo environments</li>
        </ul>
        
        <hr/>
        <p>For custom Odoo integrations and CRM enhancements, visit <a href="https://creyox.com">creyox.com</a></p>
        <p>Watch the youtube video, visit <a href="https://youtu.be/nrx0jOLKkdI">https://www.youtube.com/@CreyoxTechnologies</a></p>
        <p>Read our blog post, visit <a href="https://creyox.com/blog/boost-sales-with-odoo-3cx-crm-integration-19/boost-sales-with-odoo-3cx-crm-integration-17">https://creyox.com/blog</a></p>
        <p>Visit Our Linkedin Page <a href="https://www.linkedin.com/company/creyox-technologies/">Creyox Technologies Linkedin Page</a></p>

 """,
    "depends": ["mail"],
    "external_dependencies": {
        "python": ["pypdfium2"],
    },
    "data": [
        "security/ir.model.access.csv",
        "views/print_engine_client_views.xml",
        "views/print_job_views.xml",
        "views/printer_printer_views.xml",
        "views/ir_actions_report_views.xml",
        "views/report_print_wizard_views.xml",
        "views/res_config_settings.xml",
    ],
    "installable": True,
    "auto_install": False,
    "application": True,
    "images": ["static/description/banner.png"],
    "assets": {
        "web.assets_backend": [
            "cr_all_in_one_direct_print/static/src/js/direct_print_action.js",
        ],
    },
    "price": 120,
    "currency": "USD"
}
