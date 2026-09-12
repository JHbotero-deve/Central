#!/bin/bash
# =========================================================
# Empaqueta la carpeta frontend/ lista para re-subir a Netlify,
# SIN generar una URL nueva (hay que arrastrarla al mismo
# proyecto ya reclamado: eloquent-fox-74fb71).
# =========================================================
set -e

cd "$(dirname "$0")"

OUT="deploy_frontend.zip"
rm -f "$OUT"

echo "→ Empaquetando frontend/ ..."
cd frontend
zip -r "../$OUT" . -x "*.DS_Store"
cd ..

echo ""
echo "Listo: $OUT"
echo ""
echo "Para publicar SIN perder la URL ya registrada en Amazon:"
echo "  1. Entrá a https://app.netlify.com/projects/eloquent-fox-74fb71/deploys"
echo "  2. Arrastrá $OUT (o la carpeta frontend/) al recuadro de deploy manual"
echo "  3. La URL sigue siendo la misma: https://eloquent-fox-74fb71.netlify.app"
echo ""
echo "(Si en cambio usás 'Netlify Drop' de nuevo, te va a crear un sitio NUEVO"
echo " con otra URL — no lo hagas, porque perderías el registro de Amazon.)"
