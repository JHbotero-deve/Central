#!/usr/bin/env python3
"""Visualizador navegable y auditoría estática del repositorio Central."""
from __future__ import annotations
import argparse, ast, html, json, re, subprocess, sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN = (
    "product-analyzer/_backup_ui/", "product-analyzer/main.py",
    "product-analyzer/requirements.txt", "product-analyzer/products.db",
    "product-analyzer/test_endpoints.py", "product-analyzer/app/test_endpoints.py",
    "package-lock.json",
)
PUBLIC_HTML = {
    "product-analyzer/frontend/index.html", "product-analyzer/frontend/tarjetas.html",
    "product-analyzer/frontend/producto.html", "product-analyzer/frontend/tienda.html",
}

def tracked_paths():
    try:
        raw = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, check=True,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout
        return sorted(ROOT / p for p in raw.decode("utf-8", "replace").split("\0") if p)
    except (OSError, subprocess.CalledProcessError):
        ignored = {".git", "node_modules", ".venv", "venv", "__pycache__", ".pytest_cache"}
        return sorted(p for p in ROOT.rglob("*") if p.is_file()
                      and not any(part in ignored for part in p.relative_to(ROOT).parts))

def group(path):
    p = path.lower()
    if p.startswith("scripts/") or "/audit_" in p: return "Scripts y auditorías"
    if p.startswith("product-analyzer/app/"): return "Backend Python"
    if "/frontend/" in p or "/headphones/src/" in p: return "Frontend"
    if p.startswith(".github/") or any(x in p for x in ("dockerfile", "docker-compose", "requirements.txt", "vercel.json", ".gitignore")): return "Infraestructura"
    if p.endswith((".md", ".txt")): return "Documentación"
    if p.endswith((".svg", ".png", ".jpg", ".jpeg", ".webp", ".woff", ".woff2")): return "Recursos"
    if p.endswith((".sql", ".db", ".sqlite", ".sqlite3")): return "Datos y migraciones"
    return "Otros"

def audit(paths):
    errors, names = [], [p.relative_to(ROOT).as_posix() for p in paths]
    for name in names:
        if any(name == item or name.startswith(item) for item in FORBIDDEN):
            errors.append(f"Archivo heredado o respaldo versionado: {name}")
        if name.lower().endswith((".db", ".sqlite", ".sqlite3", "_actual.txt")):
            errors.append(f"Base de datos local o snapshot versionado: {name}")
    for path, name in zip(paths, names):
        try: source = path.read_text(encoding="utf-8-sig")
        except (UnicodeDecodeError, OSError): continue
        if path.suffix.lower() == ".py":
            try: ast.parse(source, filename=name)
            except SyntaxError as exc: errors.append(f"Python inválido {name}:{exc.lineno}: {exc.msg}")
        elif path.suffix.lower() == ".json":
            try: json.loads(source)
            except json.JSONDecodeError as exc: errors.append(f"JSON inválido {name}:{exc.lineno}:{exc.colno}: {exc.msg}")
        elif path.suffix.lower() == ".html" and name in PUBLIC_HTML:
            markup = re.sub(r"<script\b[^>]*>[\s\S]*?</script\s*>", "", source, flags=re.I)
            markup = re.sub(r"<style\b[^>]*>[\s\S]*?</style\s*>", "", markup, flags=re.I)
            markup = re.sub(r"<!--[\s\S]*?-->", "", markup)
            ids = re.findall(r'\bid\s*=\s*["\']([^"\']+)["\']', markup, flags=re.I)
            dup = sorted({item for item in ids if ids.count(item) > 1})
            if dup: errors.append(f"IDs HTML duplicados {name}: {', '.join(dup)}")
    required = (".github/workflows/ci.yml", "product-analyzer/app/api.py",
                "product-analyzer/app/main.py", "product-analyzer/frontend/index.html",
                "product-analyzer/frontend/tienda.html", "product-analyzer/frontend/producto.html")
    errors.extend(f"Falta archivo esencial: {item}" for item in required if item not in names)
    return errors

def make_html(paths, errors):
    rows, ext_counts, group_counts, total = [], Counter(), Counter(), 0
    for path in paths:
        if not path.is_file(): continue
        name = path.relative_to(ROOT).as_posix()
        ext = path.suffix.lower() or "(sin extensión)"
        category = group(name)
        try:
            raw = path.read_bytes(); size = len(raw)
            lines = raw.count(b"\n") + (1 if raw and not raw.endswith(b"\n") else 0)
        except OSError: size, lines = 0, 0
        total += size; ext_counts[ext] += 1; group_counts[category] += 1
        rows.append({"path":name,"category":category,"ext":ext,"size":size,"lines":lines,"url":name})
    data = json.dumps(rows, ensure_ascii=False).replace("</", "<\\/")
    issues = "".join("<li>"+html.escape(e)+"</li>" for e in errors) or "<li>Sin hallazgos en las comprobaciones de este auditor.</li>"
    cats = "".join("<li>"+html.escape(k)+" <b>"+str(v)+"</b></li>" for k,v in group_counts.most_common())
    exts = "".join("<li>"+html.escape(k)+" <b>"+str(v)+"</b></li>" for k,v in ext_counts.most_common())
    state = "CON HALLAZGOS" if errors else "REVISIÓN ESTÁTICA LIMPIA"
    color = "#ff9292" if errors else "#b6f23a"
    return f"""<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Central · Visualizador de código</title><style>
:root{{color-scheme:dark;--bg:#101318;--panel:#191f28;--line:#303947;--text:#edf2f7;--muted:#a7b2c2;--accent:#b6f23a}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--text);font:14px/1.5 system-ui,Segoe UI,sans-serif}}
header{{padding:28px clamp(16px,4vw,48px);border-bottom:1px solid var(--line);background:#151a22}}h1{{margin:0;font-size:clamp(24px,4vw,36px)}}p{{color:var(--muted)}}
main{{padding:24px clamp(16px,4vw,48px);max-width:1600px;margin:auto}}.stats{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-bottom:20px}}
.card{{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:16px;margin-bottom:12px}}small{{color:var(--muted)}}.num{{font-size:27px;font-weight:750}}
.layout{{display:grid;grid-template-columns:minmax(0,1fr) 300px;gap:18px}}@media(max-width:900px){{.layout{{grid-template-columns:1fr}}}}
.toolbar{{display:flex;gap:10px;margin:14px 0;flex-wrap:wrap}}input,select{{background:#0d1117;color:var(--text);border:1px solid var(--line);border-radius:8px;padding:11px}}input{{flex:1;min-width:200px}}
.scroll{{overflow:auto;max-height:70vh;border:1px solid var(--line);border-radius:12px}}table{{width:100%;border-collapse:collapse;background:var(--panel)}}th,td{{padding:10px 12px;text-align:left;border-bottom:1px solid var(--line)}}th{{color:var(--muted);position:sticky;top:0;background:var(--panel)}}
a{{color:var(--accent);text-decoration:none;overflow-wrap:anywhere}}ul{{list-style:none;padding:0;margin:0}}li{{padding:8px 0;border-bottom:1px solid var(--line);overflow-wrap:anywhere}}li:last-child{{border:0}}.issues li{{color:#ff9292}}.pill{{display:inline-block;padding:5px 10px;border-radius:99px;background:{color};color:#111;font-weight:800}}
</style></head><body><header><h1>Central · Visualizador de código</h1><p>Inventario navegable del repositorio, archivos por área y controles de higiene estática.</p><span class="pill">{state}</span></header><main>
<div class="stats"><div class="card"><small>Archivos inventariados</small><div class="num">{len(rows)}</div></div><div class="card"><small>Tamaño total</small><div class="num">{total/1024:.1f} KB</div></div><div class="card"><small>Errores estáticos</small><div class="num">{len(errors)}</div></div><div class="card"><small>Extensiones</small><div class="num">{len(ext_counts)}</div></div></div>
<div class="layout"><section><div class="toolbar"><input id="q" type="search" placeholder="Buscar archivo, carpeta o extensión…"><select id="cat"><option value="">Todas las categorías</option>{''.join('<option>'+html.escape(k)+'</option>' for k in sorted(group_counts))}</select></div>
<div class="scroll"><table><thead><tr><th>Archivo</th><th>Área</th><th>Líneas</th><th>Tamaño</th></tr></thead><tbody id="files"></tbody></table></div><p id="count"></p></section>
<aside><div class="card"><h2>Auditoría</h2><ul class="issues">{issues}</ul></div><div class="card"><h2>Por área</h2><ul>{cats}</ul></div><div class="card"><h2>Por extensión</h2><ul>{exts}</ul></div></aside></div>
<p><small>El informe valida sintaxis Python, JSON, IDs de las cuatro páginas públicas, archivos esenciales y residuos conocidos. La CI complementa el resultado con Node.js, pruebas de contrato, auditorías de catálogo, dependencias y builds Docker. No sustituye las pruebas de credenciales reales ni la revisión visual en navegador.</small></p></main>
<script>const files={data},tbody=document.getElementById("files"),q=document.getElementById("q"),cat=document.getElementById("cat"),count=document.getElementById("count");
function render(){{const query=q.value.trim().toLowerCase(),area=cat.value,shown=files.filter(f=>(!area||f.category===area)&&(!query||(f.path+" "+f.category+" "+f.ext).toLowerCase().includes(query)));tbody.innerHTML=shown.map(f=>"<tr><td><a href=\\""+f.url+"\\" target=\\"_blank\\" rel=\\"noopener\\">"+f.path.replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;")+"</a></td><td>"+f.category+"</td><td>"+f.lines.toLocaleString("es-CO")+"</td><td>"+(f.size/1024).toFixed(1)+" KB</td></tr>").join("");count.textContent=shown.length+" de "+files.length+" archivos";}}
q.addEventListener("input",render);cat.addEventListener("change",render);render();</script></body></html>"""

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Devuelve error si hay hallazgos.")
    parser.add_argument("--output", type=Path, default=ROOT / "visualizador-codigo.html")
    args = parser.parse_args()
    paths = tracked_paths()
    errors = audit(paths)
    output = args.output if args.output.is_absolute() else ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(make_html(paths, errors), encoding="utf-8")
    print(f"Visualizador: {output}\nArchivos revisados: {len(paths)}\nHallazgos: {len(errors)}")
    for issue in errors: print("[ERROR] " + issue)
    return 1 if args.check and errors else 0

if __name__ == "__main__":
    raise SystemExit(main())
