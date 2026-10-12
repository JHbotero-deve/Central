#!/usr/bin/env python3
"""Comprueba salvaguardas de los scripts de prueba y del contenedor worker."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]

def check(condition, message):
    print(f"[{'PASS' if condition else 'FAIL'}] {message}")
    if not condition:
        sys.exit(1)

demo = (ROOT / "product-analyzer/app/seed_500_demo.py").read_text(encoding="utf-8")
wompi = (ROOT / "product-analyzer/app/seed_wompi_test.py").read_text(encoding="utf-8")
docker = (ROOT / "product-analyzer/Dockerfile").read_text(encoding="utf-8")
workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
check('CENTRAL_ALLOW_DEMO_SEED' in demo and 'parser.error(' in demo,
      "la carga de 500 productos de demostración requiere habilitación explícita")
check('CENTRAL_ALLOW_WOMPI_TEST_SEED' in wompi and 'if __name__ == "__main__"' in wompi,
      "la carga de prueba Wompi no se ejecuta al importar el módulo y requiere habilitación explícita")
check('COPY app/requirements.txt ./requirements.txt' in docker and 'COPY app/ .' in docker,
      "la imagen worker instala dependencias del backend y copia el código ejecutable")
check('Build worker image' in workflow and 'python scripts/audit_seed_safety.py' in workflow,
      "CI construye y audita la imagen worker además de la API")
