# -*- coding: utf-8 -*-
"""Pure-python classification helpers (no ORM): map GL accounts to cost buckets
and analytic accounts to branch / factory / department kinds.

The rules live in ``data/classification_rules.json`` so they can be tuned without
touching code. Everything here is deterministic and unit-testable.
"""
import json
import re
from functools import lru_cache

from odoo.tools import file_open

INCOME_TYPES = ("income", "income_other")
COST_TYPES = ("expense_direct_cost", "expense", "expense_depreciation")
PL_TYPES = INCOME_TYPES + COST_TYPES

# P&L section of each Odoo account type (mirrors Odoo's own Profit & Loss report)
SECTION_OF_TYPE = {
    "income": "revenue",
    "income_other": "other_income",
    "expense_direct_cost": "cogs",
    "expense": "opex",
    "expense_depreciation": "opex",
}

_DIACRITICS = re.compile("[ً-ٟـ]")
_PUNCT = re.compile(r"[-_/\\().,:;|]+")


def normalize(text):
    """Lower-case + Arabic letter normalization used by every matcher."""
    text = str(text or "").lower()
    text = _DIACRITICS.sub("", text)
    text = re.sub("[إأآٱ]", "ا", text)
    text = text.replace("ة", "ه").replace("ى", "ي")
    text = _PUNCT.sub(" ", text)
    return " ".join(text.split())


def _compile_words(words):
    """Return (substrings, whole_words) tuples of normalized patterns."""
    subs, whole = [], []
    for word in words or []:
        if word.startswith("="):
            whole.append(normalize(word[1:]))
        else:
            subs.append(normalize(word))
    return tuple(w for w in subs if w), tuple(w for w in whole if w)


@lru_cache(maxsize=1)
def load_rules():
    with file_open("executive_company_cost_dashboard/data/classification_rules.json", "rb") as fd:
        raw = json.loads(fd.read().decode("utf-8"))

    def prep(rule):
        subs, whole = _compile_words(rule.get("words"))
        return {
            "bucket": rule["bucket"],
            "types": tuple(rule.get("types") or ()),
            "prefixes": tuple(rule.get("prefixes") or ()),
            "subs": subs,
            "whole": whole,
        }

    analytic = raw.get("analytic", {})
    return {
        "income": [prep(r) for r in raw.get("income_rules", [])],
        "cost": [prep(r) for r in raw.get("cost_rules", [])],
        "fallback": raw.get("fallback", {}),
        "branch_re": [re.compile(normalize_regex(p)) for p in analytic.get("branch_patterns", [])],
        "dept_override": [normalize(p) for p in analytic.get("department_override", [])],
        "factory_re": [re.compile(normalize_regex(p)) for p in analytic.get("factory_patterns", [])],
        "ignore_re": [re.compile(normalize_regex(p)) for p in analytic.get("ignore_patterns", [])],
        "subs": {
            bucket: [
                {"key": r["key"], "subs": _compile_words(r["words"])[0], "whole": _compile_words(r["words"])[1]}
                for r in rules
            ]
            for bucket, rules in raw.get("subcategories", {}).items()
        },
        "aliases": [
            {"subs": _compile_words(a["words"])[0], "alias": a["alias"]} for a in raw.get("aliases", [])
        ],
        "platforms": [
            {"key": p["key"], "name": p["name"], "subs": _compile_words(p["words"])[0]}
            for p in raw.get("platforms", [])
        ],
    }


def normalize_regex(pattern):
    """Normalize the literal Arabic characters of a regex without breaking its syntax."""
    return re.sub("[إأآٱ]", "ا", pattern).replace("ة", "ه").replace("ى", "ي").lower()


def _matches(rule, code, padded):
    if rule["prefixes"] and code and code.startswith(rule["prefixes"]):
        return True
    if any(w in padded for w in rule["subs"]):
        return True
    return any(" %s " % w in padded for w in rule["whole"])


def classify_account(code, name, account_type):
    """Return the bucket code of a P&L account, or None for non P&L accounts."""
    if account_type not in PL_TYPES:
        return None
    rules = load_rules()
    code = str(code or "").strip()
    # "-تشغيل" (production) mirrors of the 71xx accounts share the same function
    clean = re.sub(r"(^| )تشغيل( |$)", " ", normalize(name))
    padded = " %s " % clean
    if account_type in INCOME_TYPES:
        if account_type == "income":
            for rule in rules["income"]:
                if _matches(rule, code, padded):
                    return rule["bucket"]
    else:
        for rule in rules["cost"]:
            if rule["types"] and account_type not in rule["types"]:
                continue
            if _matches(rule, code, padded):
                return rule["bucket"]
    return rules["fallback"].get(account_type)


def classify_analytic(name):
    """Return (kind, short_name, region) for an analytic account name.

    kind is one of: branch, factory, department, other.
    """
    rules = load_rules()
    raw = str(name or "")
    norm = normalize(raw)
    parts = [p.strip() for p in re.split(r"\s/\s", raw) if p.strip()]
    short = parts[-1] if parts else raw
    region_match = re.search(r"منطقه\s*(\d+)", norm)
    region = region_match.group(1) if region_match else ""

    if not norm or any(r.search(norm) for r in rules["ignore_re"]):
        return "other", short, ""
    if any(p in norm for p in rules["dept_override"]):
        return "department", short, ""
    if any(r.search(norm) for r in rules["branch_re"]):
        return "branch", short, region
    if any(r.search(norm) for r in rules["factory_re"]):
        return "factory", short, ""
    return "department", short, ""


def classify_sub(bucket, name):
    """Sub-category key (SSC, HEALTH, ELECTRICITY, ...) of an account inside a bucket, or 'OTHER'."""
    clean = re.sub(r"(^| )تشغيل( |$)", " ", normalize(name))
    padded = " %s " % clean
    for rule in load_rules()["subs"].get(bucket, []):
        if any(w in padded for w in rule["subs"]) or any(" %s " % w in padded for w in rule["whole"]):
            return rule["key"]
    return "OTHER"


def search_aliases(name):
    """English search terms for an (Arabic) account name, so 'internet' finds 'مصروف انترنت'."""
    padded = " %s " % re.sub(r"(^| )تشغيل( |$)", " ", normalize(name))
    found = [a["alias"] for a in load_rules()["aliases"] if any(w in padded for w in a["subs"])]
    return " ".join(found)


def platform_of(name):
    """Delivery platform key (talabat / careem / ...) an account name refers to, or None."""
    norm = normalize(name)
    for platform in load_rules()["platforms"]:
        if any(w in norm for w in platform["subs"]):
            return platform["key"]
    return None
