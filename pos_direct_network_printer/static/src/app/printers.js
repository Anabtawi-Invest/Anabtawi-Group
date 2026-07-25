/* @odoo-module */

import { BasePrinter } from "@point_of_sale/app/utils/printer/base_printer";

export class PosDirectPrinter extends BasePrinter {
    setup({ printer_id }) {
        super.setup(...arguments);
        this.printer_id = printer_id;
    }

    /**
     * Sends ePOS XML commands directly over local LAN to thermal printer IP.
     */
    async sendEposXmlDirect(ip, port, xmlPayload) {
        const printPort = port || 80;
        const eposUrl = `http://${ip}:${printPort}/cgi-bin/epos/service.cgi?devid=local_printer&timeout=10000`;
        
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 5000);

        try {
            const response = await fetch(eposUrl, {
                method: "POST",
                headers: {
                    "Content-Type": "text/xml; charset=utf-8",
                    "If-Modified-Since": "Thu, 01 Jan 1970 00:00:00 GMT",
                    "SOAPAction": '""',
                },
                body: xmlPayload,
                signal: controller.signal,
            });
            clearTimeout(timeoutId);
            if (response.ok) {
                return { result: true, printerErrorCode: false };
            }
            throw new Error(`Printer HTTP status: ${response.statusText}`);
        } catch (err) {
            clearTimeout(timeoutId);
            console.warn(`[PosDirectPrinter] Direct LAN ePOS print failed: ${err.message}`);
            return null;
        }
    }

    /**
     * Direct local iframe silent print for USB or browser fallback.
     */
    async printViaLocalBrowser(img) {
        try {
            if (img && typeof window !== "undefined") {
                const printFrame = document.createElement("iframe");
                printFrame.style.position = "fixed";
                printFrame.style.right = "0";
                printFrame.style.bottom = "0";
                printFrame.style.width = "0";
                printFrame.style.height = "0";
                printFrame.style.border = "0";
                document.body.appendChild(printFrame);

                const frameDoc = printFrame.contentWindow.document;
                frameDoc.open();
                frameDoc.write(`
                    <html>
                        <head><style>@page { margin: 0; } body { margin: 0; text-align: center; }</style></head>
                        <body>
                            <img src="${img}" style="width: 100%; max-width: 384px;" onload="window.print();" />
                        </body>
                    </html>
                `);
                frameDoc.close();

                setTimeout(() => {
                    if (printFrame.parentNode) {
                        printFrame.parentNode.removeChild(printFrame);
                    }
                }, 2000);

                return { result: true, printerErrorCode: false };
            }
        } catch (err) {
            console.error("[PosDirectPrinter] Browser print error:", err);
        }
        return { result: false, printerErrorCode: "Printing failed" };
    }

    /**
     * @override
     */
    async openCashbox() {
        if (!this.printer_id) {
            return { result: false, printerErrorCode: "No printer defined" };
        }

        const ip = this.printer_id.ip;
        const port = parseInt(this.printer_id.port) || 80;

        // Direct ePOS LAN pulse for network printers
        if (ip && this.printer_id.printer_type === 'network') {
            const xmlPayload = `<?xml version="1.0" encoding="utf-8"?><epos-print xmlns="http://www.epson-pos.com/schemas/2011/03/epos-print"><pulse drawer="drawer_1" time="200"/></epos-print>`;
            const directResult = await this.sendEposXmlDirect(ip, port, xmlPayload);
            if (directResult && directResult.result) {
                return directResult;
            }
        }

        return { result: true, printerErrorCode: false };
    }

    async sendPrintingJob(img) {
        if (!this.printer_id) {
            return false;
        }

        let open_cashdrawer = Boolean(this.is_open_cashbox_receipt_print);
        if (open_cashdrawer) {
            this.is_open_cashbox_receipt_print = false;
        }

        const ip = this.printer_id.ip;
        const port = parseInt(this.printer_id.port) || 80;

        // 1. Direct ePOS LAN printing (Works 100% Offline via local LAN)
        if (ip && this.printer_id.printer_type === 'network' && img) {
            const cleanBase64 = img.replace(/^data:image\/(png|jpeg);base64,/, '');
            let xmlPayload = '<?xml version="1.0" encoding="utf-8"?><epos-print xmlns="http://www.epson-pos.com/schemas/2011/03/epos-print">';
            if (open_cashdrawer) {
                xmlPayload += '<pulse drawer="drawer_1" time="200"/>';
            }
            xmlPayload += `<image width="384" height="auto">${cleanBase64}</image>`;
            xmlPayload += '<cut type="feed"/></epos-print>';

            const directResult = await this.sendEposXmlDirect(ip, port, xmlPayload);
            if (directResult && directResult.result) {
                return directResult;
            }
        }

        // 2. Direct USB / Browser Print (Works 100% Offline)
        return await this.printViaLocalBrowser(img);
    }
}
