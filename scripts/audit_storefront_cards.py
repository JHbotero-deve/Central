#!/usr/bin/env python3
"""Regression audit for the real public storefront card markup and styles.

This guards against changing the live HTML template without updating the CSS
selectors that are actually loaded by /tienda.
"""
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "product-analyzer" / "frontend" / "tienda.html"


def fail(message: str) -> None:
    print(f"[FAIL] {message}")
    raise SystemExit(1)


if not PAGE.is_file():
    fail(f"Public storefront not found: {PAGE}")

html = PAGE.read_text(encoding="utf-8-sig")
style_match = re.search(r"<style\b[^>]*>([\s\S]*?)</style\s*>", html, re.IGNORECASE)
if not style_match:
    fail("The public storefront has no inline stylesheet.")
styles = style_match.group(1)

start = html.find("function card(p){")
end = html.find("function renderGrid(){", start)
if start < 0 or end < 0:
    fail("Could not locate the public product-card template.")
card = html[start:end]
template_start = card.find("  return ")
if template_start < 0:
    fail("The card template has no return expression.")
template = card[template_start:]

required_selectors = (
    r"\.card-footer\s*\{",
    r"\.card-actions\s*\{",
    r"\.card-action\s*\{",
    r"\.card-action-secondary\s*\{",
    r"\.card-action-primary\s*\{",
)
for selector in required_selectors:
    if not re.search(selector, styles):
        fail(f"Missing live storefront CSS selector: {selector}")

checks = {
    "card contains a full media area": 'class="card-media"' in template,
    "card has a separate bottom footer": 'class="card-footer"' in template,
    "price is rendered in the footer": 'class="card-price"' in template,
    "the first action has matching styles": 'class="card-action card-action-secondary"' in template,
    "the conditional second action is inserted once": template.count("second+") == 1,
    "footer places both actions in one action row": 'class="card-actions"' in template,
    "product image keeps its aspect ratio": bool(
        re.search(r"\.card-media>img\s*\{[^}]*object-fit\s*:\s*contain", styles)
    ),
    "affiliate URL remains a fallback": "window.location.href=p.affiliate_url||p.product_url" in html,
}

for label, ok in checks.items():
    print(f"[{'PASS' if ok else 'FAIL'}] {label}")
    if not ok:
        sys.exit(1)

print(f"[PASS] Storefront card contract validated: {PAGE.relative_to(ROOT)}")
