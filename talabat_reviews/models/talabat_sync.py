# -*- coding: utf-8 -*-
import json
import logging
import re
from datetime import datetime
from html import unescape
from urllib.parse import quote

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

PARTNER_BASE = "https://partner-app.talabat.com"


class TalabatSyncMixin(models.AbstractModel):
    _name = "talabat.sync.mixin"
    _description = "Talabat Sync Helpers"

    @api.model
    def _talabat_icp(self, key, default=""):
        return self.env["ir.config_parameter"].sudo().get_param(key, default)

    @api.model
    def _talabat_set_icp(self, key, value):
        self.env["ir.config_parameter"].sudo().set_param(key, value or "")

    @api.model
    def _talabat_session_headers(self):
        cookie = (self._talabat_icp("talabat_reviews.session_cookie") or "").strip()
        if not cookie:
            raise UserError(_(
                "Talabat session cookie is missing. Open Settings → Talabat Reviews, "
                "paste a fresh cookie from a logged-in browser, then sync again."
            ))
        return {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,ar;q=0.8",
            "Cookie": cookie,
            "Referer": PARTNER_BASE + "/",
        }

    @api.model
    def _talabat_http_get(self, path_or_url, timeout=60):
        import urllib.request

        url = path_or_url if path_or_url.startswith("http") else PARTNER_BASE + path_or_url
        headers = self._talabat_session_headers()
        req = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read().decode("utf-8", errors="replace")
                final_url = resp.geturl()
                status = getattr(resp, "status", 200)
        except Exception as exc:
            raise UserError(_("Talabat HTTP request failed: %s") % exc) from exc
        if "/login" in final_url or "/2fa" in final_url:
            self._talabat_set_icp("talabat_reviews.sync_status", "session_expired")
            self._talabat_set_icp(
                "talabat_reviews.sync_message",
                _("Session expired. Paste a new cookie after logging in (2FA if asked)."),
            )
            raise UserError(_(
                "Talabat session expired or requires 2FA. "
                "Log in at partner-app.talabat.com, copy the Cookie header, "
                "and save it in Settings → Talabat Reviews."
            ))
        if status >= 400:
            raise UserError(_("Talabat returned HTTP %s for %s") % (status, url))
        return body, final_url

    @api.model
    def _parse_review_datetime(self, raw):
        """Parse portal stamps like '11/23/2026 • 07:37 AM'."""
        if not raw:
            return False
        text = unescape(raw).replace("\u2022", " ").replace("•", " ")
        text = re.sub(r"\s+", " ", text).strip()
        for fmt in (
            "%m/%d/%Y %I:%M %p",
            "%d/%m/%Y %I:%M %p",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%dT%H:%M:%SZ",
        ):
            try:
                return datetime.strptime(text[:19] if "T" in text else text, fmt)
            except ValueError:
                continue
        # Strip trailing order number if glued
        m = re.match(
            r"(\d{1,2}/\d{1,2}/\d{4})\s+(\d{1,2}:\d{2}\s*[AP]M)",
            text,
            flags=re.I,
        )
        if m:
            try:
                return datetime.strptime(f"{m.group(1)} {m.group(2).upper()}", "%m/%d/%Y %I:%M %p")
            except ValueError:
                pass
        return False

    @api.model
    def _upsert_store(self, vals):
        Store = self.env["talabat.store"].sudo()
        vendor_id = vals.get("vendor_id")
        store = Store.search([("vendor_id", "=", vendor_id)], limit=1)
        if store:
            store.write(vals)
        else:
            store = Store.create(vals)
        return store

    @api.model
    def _upsert_review(self, store, vals, lines=None):
        Review = self.env["talabat.review"].sudo()
        order_number = str(vals.get("order_number") or "").strip()
        if not order_number:
            return Review.browse()
        review = Review.search([
            ("store_id", "=", store.id),
            ("order_number", "=", order_number),
        ], limit=1)
        payload = dict(vals)
        payload["store_id"] = store.id
        if review:
            review.write(payload)
        else:
            review = Review.create(payload)
        if lines is not None:
            review.line_ids.unlink()
            Line = self.env["talabat.review.line"].sudo()
            for line in lines:
                name = (line.get("product_name") or "").strip()
                if not name:
                    continue
                Line.create({
                    "review_id": review.id,
                    "product_name": name,
                    "quantity": line.get("quantity") or 1.0,
                    "unit_price": line.get("unit_price") or 0.0,
                })
        return review

    @api.model
    def import_payload(self, payload):
        """Import structured JSON: {stores:[{... reviews:[{..., lines:[...]}]}]}."""
        if isinstance(payload, str):
            payload = json.loads(payload)
        stores_data = payload.get("stores") or []
        store_count = review_count = line_count = 0
        for s in stores_data:
            store = self._upsert_store({
                "name": s.get("name") or s.get("vendor_id"),
                "vendor_id": s["vendor_id"],
                "store_rating": s.get("store_rating") or 0.0,
                "review_count": s.get("review_count") or 0,
                "one_star_count": s.get("one_star_count") or s.get("star_1_count") or 0,
                "star_5_count": s.get("star_5_count") or 0,
                "star_4_count": s.get("star_4_count") or 0,
                "star_3_count": s.get("star_3_count") or 0,
                "star_2_count": s.get("star_2_count") or 0,
                "star_1_count": s.get("star_1_count") or s.get("one_star_count") or 0,
                "summary_text": s.get("summary_text") or "",
                "last_sync_at": fields.Datetime.now(),
                "pos_config_id": s.get("pos_config_id") or False,
            })
            store_count += 1
            for r in s.get("reviews") or []:
                dt = r.get("review_datetime")
                if isinstance(dt, str):
                    dt = self._parse_review_datetime(dt) or fields.Datetime.to_datetime(dt)
                review = self._upsert_review(store, {
                    "order_number": str(r.get("order_number")),
                    "review_datetime": dt or fields.Datetime.now(),
                    "rating": int(r.get("rating") or 0),
                    "comment": r.get("comment") or "",
                    "can_reply": bool(r.get("can_reply", True)),
                    "can_dispute": bool(r.get("can_dispute", False)),
                    "replied": bool(r.get("replied", False)),
                    "disputed": bool(r.get("disputed", False)),
                    "external_uid": r.get("external_uid") or False,
                }, lines=r.get("lines"))
                review_count += 1
                line_count += len(review.line_ids)
        return {
            "stores": store_count,
            "reviews": review_count,
            "lines": line_count,
        }

    @api.model
    def _parse_stores_list_html(self, html):
        """Extract store cards from /reviews list page."""
        stores = []
        # vendor links: /reviews/TB_JO;629658
        for m in re.finditer(
            r'href=["\']/reviews/(TB_[A-Z]{2};[0-9]+)["\'][^>]*>[\s\S]*?</a>',
            html,
            flags=re.I,
        ):
            vendor_id = m.group(1)
            block = m.group(0)
            name_m = re.search(r"(Al Anabtawi Sweets[^<]{0,80})", block)
            name = unescape(name_m.group(1)).strip() if name_m else vendor_id
            rating_m = re.search(r"Store rating[\s\S]{0,80}?([0-9]+(?:\.[0-9]+)?)", block, re.I)
            reviews_m = re.search(r"No\.?\s*of reviews[\s\S]{0,80}?([0-9]+)", block, re.I)
            one_m = re.search(r"1-star ratings[\s\S]{0,80}?([0-9]+)", block, re.I)
            stores.append({
                "vendor_id": vendor_id,
                "name": name,
                "store_rating": float(rating_m.group(1)) if rating_m else 0.0,
                "review_count": int(reviews_m.group(1)) if reviews_m else 0,
                "one_star_count": int(one_m.group(1)) if one_m else 0,
                "star_1_count": int(one_m.group(1)) if one_m else 0,
            })
        # Fallback: text scrape when SPA shell has hydrated content in body text only
        if not stores:
            for m in re.finditer(
                r"(Al Anabtawi Sweets[^\n]{0,80})\s+Store rating\s+([0-9.]+)\s+No\. of reviews\s+(\d+)\s+1-star ratings\s+(\d+)",
                html,
                flags=re.I,
            ):
                stores.append({
                    "vendor_id": "NAME:%s" % m.group(1).strip()[:60],
                    "name": m.group(1).strip(),
                    "store_rating": float(m.group(2)),
                    "review_count": int(m.group(3)),
                    "one_star_count": int(m.group(4)),
                    "star_1_count": int(m.group(4)),
                })
        # Deduplicate by vendor_id
        seen = {}
        for s in stores:
            seen[s["vendor_id"]] = s
        return list(seen.values())

    @api.model
    def _parse_store_reviews_html(self, html, vendor_id):
        """Parse a single store reviews page."""
        result = {
            "vendor_id": vendor_id,
            "name": vendor_id,
            "store_rating": 0.0,
            "review_count": 0,
            "one_star_count": 0,
            "star_5_count": 0,
            "star_4_count": 0,
            "star_3_count": 0,
            "star_2_count": 0,
            "star_1_count": 0,
            "summary_text": "",
            "reviews": [],
        }
        name_m = re.search(r"(Al Anabtawi Sweets[^<\n]{0,80})", html)
        if name_m:
            result["name"] = unescape(name_m.group(1)).strip()
        rating_m = re.search(r"Store rating\s*([0-9]+(?:\.[0-9]+)?)", html, re.I)
        if rating_m:
            result["store_rating"] = float(rating_m.group(1))
        count_m = re.search(r"([0-9]+)\s+reviews", html, re.I)
        if count_m:
            result["review_count"] = int(count_m.group(1))
        for stars, key in ((5, "star_5_count"), (4, "star_4_count"), (3, "star_3_count"),
                           (2, "star_2_count"), (1, "star_1_count")):
            m = re.search(rf"{stars}\s*stars?\s*([0-9]+)", html, re.I)
            if m:
                result[key] = int(m.group(1))
        result["one_star_count"] = result["star_1_count"]
        sum_m = re.search(
            r"Reviews summary[\s\S]{0,40}?(Based on[\s\S]{20,500}?)(?:Last \d|Search in reviews|\d{1,2}/\d{1,2}/\d{4})",
            html,
            re.I,
        )
        if sum_m:
            result["summary_text"] = re.sub(r"\s+", " ", unescape(sum_m.group(1))).strip()

        # Rows: date • time • order \n comment
        row_re = re.compile(
            r"(\d{1,2}/\d{1,2}/\d{4})\s*[•\u2022]\s*(\d{1,2}:\d{2}\s*[AP]M)\s*[•\u2022]\s*(\d{6,})"
            r"\s*([\s\S]{0,400}?)(?=(?:Reply|View order|Dispute|\d{1,2}/\d{1,2}/\d{4}\s*[•\u2022]|Reviews per page|$))",
            re.I,
        )
        for m in row_re.finditer(html):
            date_s, time_s, order_no, rest = m.groups()
            comment = unescape(rest)
            comment = re.sub(r"<[^>]+>", " ", comment)
            comment = re.sub(r"\b(Reply|View order|Dispute)\b", " ", comment, flags=re.I)
            comment = re.sub(r"\s+", " ", comment).strip()
            # Heuristic rating: dispute button often on low reviews; default 1 if dispute nearby else try stars in block
            block = m.group(0)
            rating = 1
            if "Dispute" not in block and comment:
                # positive short comments without dispute → treat as 5 if word-like praise else 4
                if re.search(r"رائع|ممتاز|يجنن|رهيب|10/10", comment):
                    rating = 5
                else:
                    rating = 4
            elif "Dispute" in block:
                rating = 1
            dt = self._parse_review_datetime(f"{date_s} {time_s}")
            result["reviews"].append({
                "order_number": order_no,
                "review_datetime": dt.strftime("%Y-%m-%d %H:%M:%S") if dt else fields.Datetime.now(),
                "rating": rating,
                "comment": comment,
                "can_reply": "Reply" in block,
                "can_dispute": "Dispute" in block,
                "replied": False,
                "lines": [],
            })
        return result

    @api.model
    def _parse_order_products_html(self, html):
        """Best-effort product extraction from View order HTML/JSON blob."""
        lines = []
        # JSON-ish product names
        for m in re.finditer(
            r'"(?:name|productName|product_name|title)"\s*:\s*"([^"]{2,120})"',
            html,
        ):
            name = unescape(m.group(1)).strip()
            if name and name.lower() not in ("talabat", "total", "subtotal"):
                lines.append({"product_name": name, "quantity": 1.0})
        # Deduplicate preserving order
        seen = set()
        unique = []
        for line in lines:
            key = line["product_name"].lower()
            if key in seen:
                continue
            seen.add(key)
            unique.append(line)
        return unique

    @api.model
    def _fetch_order_lines(self, vendor_id, order_number):
        """Try known partner paths for order detail; return product lines."""
        candidates = [
            f"/orders/{order_number}",
            f"/order-history/{order_number}",
            f"/reviews/{quote(vendor_id, safe=';')}/orders/{order_number}",
            f"/server-routes/api/orders/{order_number}",
        ]
        for path in candidates:
            try:
                body, final_url = self._talabat_http_get(path)
            except UserError:
                continue
            if "/login" in final_url:
                raise UserError(_("Talabat session expired while loading order %s.") % order_number)
            lines = self._parse_order_products_html(body)
            if lines:
                return lines
        return []

    @api.model
    def sync_reviews(self, fetch_order_lines=True, max_orders_for_lines=80):
        """Pull stores + reviews from the partner portal using the saved session cookie."""
        self._talabat_set_icp("talabat_reviews.sync_status", "running")
        self._talabat_set_icp("talabat_reviews.sync_message", _("Sync started…"))
        try:
            list_html, _ = self._talabat_http_get("/reviews")
            stores = self._parse_stores_list_html(list_html)
            if not stores:
                # SPA may need direct vendor sync from already known stores
                stores = [{
                    "vendor_id": s.vendor_id,
                    "name": s.name,
                    "store_rating": s.store_rating,
                    "review_count": s.review_count,
                    "one_star_count": s.one_star_count,
                    "star_1_count": s.one_star_count,
                } for s in self.env["talabat.store"].sudo().search([])]
            if not stores:
                raise UserError(_(
                    "No stores found on /reviews. The partner app may be client-rendered. "
                    "Use Talabat → Import Reviews JSON, or keep store records and retry."
                ))

            payload_stores = []
            orders_fetched = 0
            for s in stores:
                vendor_id = s["vendor_id"]
                if vendor_id.startswith("NAME:"):
                    # Cannot open detail without real vendor id
                    payload_stores.append({**s, "reviews": []})
                    continue
                detail_html, _ = self._talabat_http_get(f"/reviews/{quote(vendor_id, safe=';')}")
                detail = self._parse_store_reviews_html(detail_html, vendor_id)
                # Prefer list-page KPIs when detail parse misses them
                for key in ("name", "store_rating", "review_count", "one_star_count"):
                    if s.get(key) and not detail.get(key):
                        detail[key] = s[key]
                if fetch_order_lines:
                    for review in detail.get("reviews") or []:
                        if orders_fetched >= max_orders_for_lines:
                            break
                        order_no = review.get("order_number")
                        if not order_no:
                            continue
                        try:
                            lines = self._fetch_order_lines(vendor_id, order_no)
                        except UserError:
                            raise
                        except Exception as exc:
                            _logger.warning("Order lines fetch failed for %s: %s", order_no, exc)
                            lines = []
                        review["lines"] = lines
                        orders_fetched += 1
                payload_stores.append(detail)

            stats = self.import_payload({"stores": payload_stores})
            msg = _(
                "Synced %(stores)s stores, %(reviews)s reviews, %(lines)s order lines."
            ) % stats
            self._talabat_set_icp("talabat_reviews.sync_status", "ok")
            self._talabat_set_icp("talabat_reviews.sync_message", msg)
            self._talabat_set_icp(
                "talabat_reviews.last_sync_at",
                fields.Datetime.to_string(fields.Datetime.now()),
            )
            return stats
        except Exception as exc:
            self._talabat_set_icp("talabat_reviews.sync_status", "error")
            self._talabat_set_icp("talabat_reviews.sync_message", str(exc))
            _logger.exception("Talabat sync failed")
            raise

    @api.model
    def cron_sync_reviews(self):
        enabled = self._talabat_icp("talabat_reviews.sync_enabled", "False")
        if enabled not in ("True", "1", "true"):
            _logger.info("Talabat reviews cron skipped (sync disabled).")
            return
        try:
            self.sync_reviews(fetch_order_lines=True)
        except Exception:
            _logger.exception("Talabat reviews cron failed")
