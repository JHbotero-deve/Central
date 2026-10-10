#!/usr/bin/env python3
"""Regression checks for Central's live dashboard and card-creation flow."""
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
FRONT = ROOT / "product-analyzer" / "frontend"


def check(condition: bool, message: str) -> None:
    print(f"[{'PASS' if condition else 'FAIL'}] {message}")
    if not condition:
        raise SystemExit(1)


page = (FRONT / "index.html").read_text(encoding="utf-8-sig")
markup = re.sub(r"<script\b[^>]*>[\s\S]*?</script\s*>", "", page, flags=re.IGNORECASE)
ids = re.findall(r'\bid=["\']([^"\']+)["\']', markup)
duplicates = sorted({item for item in ids if ids.count(item) > 1})
check(not duplicates, "dashboard has no duplicate static HTML IDs")
check(len(re.findall(r'<section\b[^>]*\bid=["\']importar["\']', markup)) == 1,
      "dashboard has exactly one #importar section")
check(len(re.findall(r'<form\b[^>]*\bid=["\']importForm["\']', markup)) == 1,
      "dashboard has exactly one importer form")
check("importImageUrl" not in page and "URL de imagen real (opcional)" not in page,
      "import flow does not ask the user to paste an image URL")
check("importTitle" not in page and "importPrice" not in page and "importCurrency" not in page,
      "import form has no stale manual override fields")
check("async function submitManual(e)" not in page,
      "unwired manual-product handler has been removed")
check("function open3dInCard(p)" not in page and ".model3d-css" not in page,
      "fake CSS-rendered product models are not in the dashboard")
tg_start = page.find("async function loadTelegram(){")
tg_end = page.find("let radarProducts=[];", tg_start)
telegram_fn = page[tg_start:tg_end]
check(tg_start >= 0 and tg_end > tg_start and "innerHTML=" not in telegram_fn,
      "Telegram refresh updates status fields without replacing section markup")

routes = (FRONT / "vercel.json").read_text(encoding="utf-8")
check(re.search(r'"source"\s*:\s*"/"\s*,\s*"destination"\s*:\s*"/index\.html"', routes) is not None,
      "root URL opens the Central dashboard")
check(re.search(r'"source"\s*:\s*"/vitrina"\s*,\s*"destination"\s*:\s*"/tienda\.html"', routes) is not None,
      "legacy vitrina URL opens the real published store")

editor = (FRONT / "tarjetas.html").read_text(encoding="utf-8-sig")
vars_start = editor.find("function renderVars(){")
vars_end = editor.find("function model(){", vars_start)
vars_fn = editor[vars_start:vars_end]
check("ed-upload-primary" in vars_fn and vars_fn.find("ed-upload-primary") < vars_fn.find("ed-image-url"),
      "card creator presents upload before optional URL entry")
check('href="/tienda">Ver tienda' in editor and 'href="/">CENTRAL' in editor,
      "editor links return to the dashboard and real public store")
check('data-tab="theme"' not in editor and "renderThemes" not in editor,
      "misleading browser-only theme tab was removed")
core = (FRONT / "shopr-core.js").read_text(encoding="utf-8")
check("THEMES" not in core and "setTheme" not in core,
      "unpersisted browser theme state was removed")

print("[PASS] Central admin flow audit complete")
