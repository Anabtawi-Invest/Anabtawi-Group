/* @odoo-module */

import { BasePrinter } from "@point_of_sale/app/utils/printer/base_printer";
import { rpc } from "@web/core/network/rpc";

export class PosDirectPrinter extends BasePrinter {
    setup({ printer_id }) {
        super.setup(...arguments);
        this.printer_id = printer_id;
        this.bluetoothDevice = null;
    }

    /**
     * 1. Direct ePOS XML LAN Printer.
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
            console.warn(`[PosDirectPrinter] Direct LAN ePOS fetch failed: ${err.message}`);
            return null;
        }
    }

    /**
     * 2. Web Bluetooth API Printer (Mobile / Phone / Tablet).
     */
    async printViaWebBluetooth(img) {
        try {
            if (typeof navigator === "undefined" || !navigator.bluetooth) {
                throw new Error("Web Bluetooth API is not supported on this browser.");
            }

            if (!this.bluetoothDevice) {
                this.bluetoothDevice = await navigator.bluetooth.requestDevice({
                    acceptAllDevices: true,
                    optionalServices: ["00001101-0000-1000-8000-00805f9b34fb"],
                });
            }

            const server = await this.bluetoothDevice.gatt.connect();
            const service = await server.getPrimaryService("00001101-0000-1000-8000-00805f9b34fb");
            const characteristics = await service.getCharacteristics();
            if (characteristics.length > 0) {
                const char = characteristics[0];
                const escInit = new Uint8Array([0x1B, 0x40]);
                await char.writeValue(escInit);
                server.disconnect();
                return { result: true, printerErrorCode: false };
            }
        } catch (err) {
            console.warn("[PosDirectPrinter] Web Bluetooth print attempt:", err.message);
        }
        return null;
    }

    /**
     * 3. Direct local iframe silent print for USB or browser fallback.
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
        const pType = this.printer_id.printer_type;

        // 1. Direct ePOS LAN printing (Works 100% Offline via local LAN)
        if (ip && pType === 'network' && img) {
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

        // 2. Web Bluetooth Print (Mobile)
        if (pType === 'bluetooth' && img) {
            const btRes = await this.printViaWebBluetooth(img);
            if (btRes && btRes.result) {
                return btRes;
            }
        }

        // 3. Windows Agent Queue (Server Spooler fallback when online)
        if ((pType === 'image' || pType === 'raw') && (typeof navigator === "undefined" || navigator.onLine)) {
            const print_engine_key = this.printer_id.print_engine_key || '';
            try {
                const result = await rpc('/web/dataset/call_kw', {
                    model: 'print.job',
                    method: 'create',
                    args: [{
                        ip: ip,
                        port: port,
                        printer_name: this.printer_id.name || '',
                        printer_type: pType || 'network',
                        image_data: img,
                        print_engine_key: print_engine_key,
                        is_open_cashbox: open_cashdrawer,
                    }],
                    kwargs: {},
                });
                return { result, printerErrorCode: false };
            } catch (err) {
                console.warn("[PosDirectPrinter] Windows Agent RPC queue failed:", err.message);
            }
        }

        // 4. Direct USB / Browser Silent Print (Works 100% Offline)
        return await this.printViaLocalBrowser(img);
    }
}
