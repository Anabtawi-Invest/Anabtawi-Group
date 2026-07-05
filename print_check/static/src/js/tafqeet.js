/**
 * Tafqeet Library - Arabic Number to Words Conversion
 * ====================================================
 * 
 * Converts numeric amounts to Arabic text for cheque writing.
 * Supports all Arab currencies with proper grammatical forms.
 * 
 * Features:
 * - Full Arabic grammar support (singular, dual, plural)
 * - Currency and fraction name handling
 * - "فقط...لا غير" surround option
 * - Numbers up to 999,999,999,999 (trillion)
 * 
 * @version 2.0.0
 * @author Agile Consulting
 */

(function(global) {
    'use strict';

    // ===========================================
    // Arabic Number Words
    // ===========================================
    
    const ONES = [
        '', 'واحد', 'اثنان', 'ثلاثة', 'أربعة', 'خمسة',
        'ستة', 'سبعة', 'ثمانية', 'تسعة', 'عشرة',
        'أحد عشر', 'اثنا عشر', 'ثلاثة عشر', 'أربعة عشر', 'خمسة عشر',
        'ستة عشر', 'سبعة عشر', 'ثمانية عشر', 'تسعة عشر'
    ];

    const TENS = [
        '', 'عشرة', 'عشرون', 'ثلاثون', 'أربعون', 'خمسون',
        'ستون', 'سبعون', 'ثمانون', 'تسعون'
    ];

    const HUNDREDS = [
        '', 'مائة', 'مائتان', 'ثلاثمائة', 'أربعمائة', 'خمسمائة',
        'ستمائة', 'سبعمائة', 'ثمانمائة', 'تسعمائة'
    ];

    // Scale words with grammatical forms
    const SCALE_WORDS = {
        thousand: {
            singular: 'ألف',
            dual: 'ألفان',
            plural: 'آلاف'
        },
        million: {
            singular: 'مليون',
            dual: 'مليونان',
            plural: 'ملايين'
        },
        billion: {
            singular: 'مليار',
            dual: 'ملياران',
            plural: 'مليارات'
        }
    };

    // ===========================================
    // Core Conversion Functions
    // ===========================================

    /**
     * Convert a number (0-999) to Arabic words
     * @param {number} num - Number between 0 and 999
     * @returns {string} Arabic text
     */
    function convertHundreds(num) {
        if (num === 0) return '';
        if (num < 20) return ONES[num];
        
        const parts = [];
        
        // Hundreds
        const hundreds = Math.floor(num / 100);
        if (hundreds > 0) {
            parts.push(HUNDREDS[hundreds]);
        }
        
        // Tens and ones
        const remainder = num % 100;
        if (remainder > 0) {
            if (remainder < 20) {
                parts.push(ONES[remainder]);
            } else {
                const tens = Math.floor(remainder / 10);
                const ones = remainder % 10;
                
                if (ones > 0) {
                    parts.push(ONES[ones] + ' و' + TENS[tens]);
                } else {
                    parts.push(TENS[tens]);
                }
            }
        }
        
        return parts.join(' و');
    }

    /**
     * Get scale word with proper grammatical form
     * @param {number} num - The number to determine form for
     * @param {object} scaleObj - Object with singular, dual, plural forms
     * @returns {string} Correct grammatical form
     */
    function getScaleWord(num, scaleObj) {
        if (num === 1) return scaleObj.singular;
        if (num === 2) return scaleObj.dual;
        if (num >= 3 && num <= 10) return scaleObj.plural;
        return scaleObj.singular; // 11+ uses singular
    }

    /**
     * Convert a whole number to Arabic words
     * @param {number} num - Non-negative integer
     * @returns {string} Arabic text representation
     */
    function tafqeet(num) {
        if (num === 0) return 'صفر';
        if (num < 0) return 'سالب ' + tafqeet(Math.abs(num));
        
        num = Math.floor(num);
        const parts = [];
        
        // Billions
        const billions = Math.floor(num / 1000000000);
        if (billions > 0) {
            if (billions === 1) {
                parts.push(SCALE_WORDS.billion.singular);
            } else if (billions === 2) {
                parts.push(SCALE_WORDS.billion.dual);
            } else {
                parts.push(convertHundreds(billions) + ' ' + getScaleWord(billions, SCALE_WORDS.billion));
            }
            num %= 1000000000;
        }
        
        // Millions
        const millions = Math.floor(num / 1000000);
        if (millions > 0) {
            if (millions === 1) {
                parts.push(SCALE_WORDS.million.singular);
            } else if (millions === 2) {
                parts.push(SCALE_WORDS.million.dual);
            } else {
                parts.push(convertHundreds(millions) + ' ' + getScaleWord(millions, SCALE_WORDS.million));
            }
            num %= 1000000;
        }
        
        // Thousands
        const thousands = Math.floor(num / 1000);
        if (thousands > 0) {
            if (thousands === 1) {
                parts.push(SCALE_WORDS.thousand.singular);
            } else if (thousands === 2) {
                parts.push(SCALE_WORDS.thousand.dual);
            } else {
                parts.push(convertHundreds(thousands) + ' ' + getScaleWord(thousands, SCALE_WORDS.thousand));
            }
            num %= 1000;
        }
        
        // Hundreds, tens, ones
        if (num > 0) {
            parts.push(convertHundreds(num));
        }
        
        return parts.join(' و');
    }

    /**
     * Convert fraction to words
     * @param {number} fraction - Fraction part (e.g., 500 for 500 fils)
     * @param {number} multiplier - Fraction multiplier (100 or 1000)
     * @returns {string} Arabic text for fraction
     */
    function tafqeetFraction(fraction, multiplier) {
        if (fraction === 0) return '';
        
        // Ensure fraction is in correct range
        fraction = Math.round(fraction);
        if (fraction < 0) fraction = 0;
        if (fraction >= multiplier) fraction = multiplier - 1;
        
        return tafqeet(fraction);
    }

    // ===========================================
    // Cheque Amount Formatting
    // ===========================================

    /**
     * Format a complete cheque amount with currency
     * @param {number} amount - The amount (e.g., 1234.567)
     * @param {object} currencyInfo - Currency configuration
     * @param {string} currencyInfo.currency - Currency name (nominative)
     * @param {string} currencyInfo.currencyAccusative - Currency name (accusative)
     * @param {string} currencyInfo.fraction - Fraction name (e.g., فلس)
     * @param {number} currencyInfo.fractionMultiplier - 100 or 1000
     * @param {object} options - Formatting options
     * @param {boolean} options.withCurrency - Include currency name
     * @param {string} options.fractionFormat - 'normal', 'words', or 'divide'
     * @param {string} options.surround - 'none' or 'faqat'
     * @returns {string} Formatted Arabic cheque amount
     */
    function formatChequeAmount(amount, currencyInfo, options = {}) {
        const {
            currency = 'دينار',
            currencyAccusative = 'ديناراً',
            fraction = 'فلس',
            fractionMultiplier = 1000
        } = currencyInfo;
        
        const {
            withCurrency = true,
            fractionFormat = 'normal',
            surround = 'faqat'
        } = options;
        
        // Split into integer and fraction parts
        const integerPart = Math.floor(amount);
        const fractionPart = Math.round((amount - integerPart) * fractionMultiplier);
        
        // Build the result
        const parts = [];
        
        // Integer part in words
        if (integerPart > 0) {
            parts.push(tafqeet(integerPart));
            if (withCurrency) {
                // Use accusative form after numbers
                parts.push(currencyAccusative);
            }
        }
        
        // Fraction part
        if (fractionPart > 0) {
            if (parts.length > 0) {
                parts.push('و');
            }
            
            if (fractionFormat === 'words') {
                parts.push(tafqeet(fractionPart));
                parts.push(fraction);
            } else if (fractionFormat === 'divide') {
                // Show as X/1000 or X/100
                parts.push(fractionPart + '/' + fractionMultiplier);
                parts.push(fraction);
            } else {
                // Normal - just the number
                parts.push(fractionPart);
                parts.push(fraction);
            }
        } else if (integerPart === 0) {
            // Zero amount
            parts.push('صفر');
            if (withCurrency) {
                parts.push(currencyAccusative);
            }
        }
        
        let result = parts.join(' ');
        
        // Apply surround
        if (surround === 'faqat') {
            result = 'فقط ' + result + ' لا غير';
        }
        
        return result;
    }

    // ===========================================
    // Exports
    // ===========================================
    
    // Export to global scope
    global.tafqeet = tafqeet;
    global.tafqeetFraction = tafqeetFraction;
    global.formatChequeAmount = formatChequeAmount;
    
    // Also export as module if available
    if (typeof module !== 'undefined' && module.exports) {
        module.exports = { tafqeet, tafqeetFraction, formatChequeAmount };
    }
    
    console.log('[Tafqeet] Library loaded');

})(typeof window !== 'undefined' ? window : this);
