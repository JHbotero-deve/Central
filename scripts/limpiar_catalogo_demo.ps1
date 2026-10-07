$ErrorActionPreference = "Stop"

$ROOT = "C:\Users\jorge\Central"
$PROJECT = "482ad1a7-cf0b-4438-9ee6-5b8952dd6d5f"
$ENVIRONMENT = "production"
$SERVICE = "gracious-renewal"

$PYTHON = Join-Path $ROOT ".venv\Scripts\python.exe"

if (-not (Test-Path $PYTHON)) {
    $PYTHON = (Get-Command python.exe -ErrorAction SilentlyContinue).Source
}

if (-not $PYTHON) {
    Write-Host "[ERROR] No se encontró Python." -ForegroundColor Red
    exit 1
}

if (-not (Get-Command npx.cmd -ErrorAction SilentlyContinue)) {
    Write-Host "[ERROR] No se encontró npx.cmd." -ForegroundColor Red
    exit 1
}

$TEMP_SCRIPT = Join-Path $env:TEMP "central_cleanup_demo_$([guid]::NewGuid().ToString('N')).py"

@'
import os
import sys
import json
from pathlib import Path
from datetime import datetime

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except Exception as exc:
    print("PSYCOPG2_ERROR=" + str(exc))
    sys.exit(20)

db_url = os.getenv("DATABASE_URL")

if not db_url:
    print("DATABASE_URL_MISSING")
    sys.exit(21)

backup_dir = Path(os.getenv("CENTRAL_BACKUP_DIR", "."))

try:
    backup_dir.mkdir(parents=True, exist_ok=True)
except Exception as exc:
    print("BACKUP_DIR_ERROR=" + str(exc))
    sys.exit(22)

stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
backup_file = backup_dir / f"central_demo_cleanup_backup_{stamp}.json"

conn = None

try:
    conn = psycopg2.connect(db_url)

    with conn.cursor(cursor_factory=RealDictCursor) as cur:

        # ----------------------------------------------------
        # 1. Identificar EXCLUSIVAMENTE los productos demo
        # ----------------------------------------------------
        cur.execute("""
            SELECT
                p.id,
                p.external_id,
                p.sku,
                p.title,
                p.platform_id,
                p.category_id,
                p.current_price,
                p.currency,
                p.product_url,
                p.is_active
            FROM products p
            WHERE
                p.external_id LIKE 'CENT-%'
                OR p.external_id = 'TEST-WOMPI-1000'
                OR p.sku LIKE 'CENT-%'
                OR p.sku = 'TEST-WOMPI-1000'
                OR p.title ILIKE 'Producto de prueba Wompi%'
            ORDER BY p.id
        """)

        products = cur.fetchall()

        if not products:
            print("DEMO_PRODUCTS=0")
            print("RESULT=NOTHING_TO_DELETE")
            sys.exit(0)

        product_ids = [int(row["id"]) for row in products]

        print("DEMO_PRODUCTS=" + str(len(product_ids)))

        for row in products:
            print(
                f"DEMO id={row['id']} "
                f"external_id={row['external_id']} "
                f"title={row['title']}"
            )

        # ----------------------------------------------------
        # 2. Buscar todas las tablas que referencian product_id
        # ----------------------------------------------------
        cur.execute("""
            SELECT
                table_schema,
                table_name
            FROM information_schema.columns
            WHERE column_name = 'product_id'
              AND table_schema = 'public'
            ORDER BY table_name
        """)

        product_tables = cur.fetchall()

        references = {}
        protected = {}

        for item in product_tables:
            table = item["table_name"]

            # Nunca eliminar directamente la tabla products aquí.
            if table == "products":
                continue

            cur.execute(
                f'''
                SELECT COUNT(*) AS n
                FROM public."{table}"
                WHERE product_id = ANY(%s)
                ''',
                (product_ids,)
            )

            count = int(cur.fetchone()["n"])

            if count:
                references[table] = count

                # Historial comercial/pagos: no tocar automáticamente.
                if any(
                    word in table.lower()
                    for word in [
                        "order",
                        "invoice",
                        "payment",
                        "transaction",
                        "reservation",
                        "sale"
                    ]
                ):
                    protected[table] = count

        print("REFERENCES=" + json.dumps(references, default=str))
        print("PROTECTED_REFERENCES=" + json.dumps(protected, default=str))

        # ----------------------------------------------------
        # 3. Seguridad:
        #    si un demo está ligado a una venta/pago/pedido,
        #    NO se elimina automáticamente.
        # ----------------------------------------------------
        if protected:
            print("RESULT=ABORT_PROTECTED_REFERENCES")
            print(
                "Se encontraron referencias comerciales. "
                "No se modificó la base de datos."
            )
            conn.rollback()
            sys.exit(30)

        # ----------------------------------------------------
        # 4. Crear respaldo de los registros afectados
        # ----------------------------------------------------
        backup = {
            "created_at": datetime.now().isoformat(),
            "product_ids": product_ids,
            "products": [dict(x) for x in products],
            "children": {}
        }

        for table, count in references.items():
            cur.execute(
                f'''
                SELECT *
                FROM public."{table}"
                WHERE product_id = ANY(%s)
                ''',
                (product_ids,)
            )

            backup["children"][table] = [
                dict(x) for x in cur.fetchall()
            ]

        backup_file.write_text(
            json.dumps(
                backup,
                ensure_ascii=False,
                indent=2,
                default=str
            ),
            encoding="utf-8"
        )

        print("BACKUP=" + str(backup_file))

        # ----------------------------------------------------
        # 5. Eliminar registros dependientes
        # ----------------------------------------------------
        deleted_children = {}

        for table in references:
            cur.execute(
                f'''
                DELETE FROM public."{table}"
                WHERE product_id = ANY(%s)
                ''',
                (product_ids,)
            )

            deleted_children[table] = cur.rowcount

        # ----------------------------------------------------
        # 6. Eliminar scores por seguridad si usan otra FK
        # ----------------------------------------------------
        # Ya está incluido si tiene product_id.
        # No se ejecutan deletes genéricos fuera de esa FK.
        # ----------------------------------------------------

        # ----------------------------------------------------
        # 7. Eliminar productos demo
        # ----------------------------------------------------
        cur.execute(
            """
            DELETE FROM products
            WHERE id = ANY(%s)
            """,
            (product_ids,)
        )

        deleted_products = cur.rowcount

        if deleted_products != len(product_ids):
            raise RuntimeError(
                f"Se esperaban {len(product_ids)} productos eliminados "
                f"pero PostgreSQL eliminó {deleted_products}."
            )

        # ----------------------------------------------------
        # 8. Confirmar transacción
        # ----------------------------------------------------
        conn.commit()

        print(
            "DELETED_CHILDREN="
            + json.dumps(deleted_children, default=str)
        )

        print("DELETED_PRODUCTS=" + str(deleted_products))
        print("RESULT=SUCCESS")

except Exception as exc:
    if conn:
        conn.rollback()

    print("RESULT=ROLLBACK")
    print("ERROR=" + repr(exc))
    sys.exit(40)

finally:
    if conn:
        conn.close()
'@ | Set-Content -Path $TEMP_SCRIPT -Encoding UTF8

try {

    Write-Host ""
    Write-Host "=============================================" -ForegroundColor Cyan
    Write-Host " CENTRAL - LIMPIEZA CATALOGO DEMO" -ForegroundColor Cyan
    Write-Host "=============================================" -ForegroundColor Cyan
    Write-Host ""

    Write-Host "[1/3] Verificando Railway CLI mediante npx..." -ForegroundColor Yellow

    & npx.cmd --yes @railway/cli --version

    if ($LASTEXITCODE -ne 0) {
        throw "No fue posible ejecutar Railway CLI mediante npx."
    }

    Write-Host ""
    Write-Host "[2/3] Ejecutando limpieza contra Railway production..." -ForegroundColor Yellow
    Write-Host ""

    # Railway run INYECTA DATABASE_URL del servicio
    # y ejecuta Python LOCALMENTE.
    & npx.cmd --yes @railway/cli run `
        --project $PROJECT `
        --environment $ENVIRONMENT `
        --service $SERVICE `
        $PYTHON $TEMP_SCRIPT

    $code = $LASTEXITCODE

    Write-Host ""

    if ($code -eq 0) {
        Write-Host "[OK] Limpieza completada." -ForegroundColor Green
    }
    else {
        Write-Host "[ERROR] La limpieza terminó con código $code." -ForegroundColor Red
        exit $code
    }

}
finally {

    Write-Host "[3/3] Eliminando archivo temporal local..." -ForegroundColor Yellow

    if (Test-Path $TEMP_SCRIPT) {
        Remove-Item $TEMP_SCRIPT -Force -ErrorAction SilentlyContinue
    }

    Write-Host ""
    Write-Host "Proceso terminado." -ForegroundColor Cyan
}

