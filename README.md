# Radar de Producto — Proyecto completo

Este paquete junta las dos partes del proyecto en un solo lugar, listo para
clonar a tu PC, subir a GitHub y correr con Docker.

## Estructura

```
proyecto-completo/
├── product-analyzer/     <- Backend (FastAPI + Postgres) + frontend + landing
│   ├── app/               API, ingesta, scoring, integraciones Amazon/TikTok
│   ├── frontend/           Dashboard (index.html) - diseño gamer
│   ├── landing/            Landing para Amazon Associates
│   ├── sql/                 Esquema de base de datos
│   ├── docker-compose.yml
│   └── README.md            Instrucciones detalladas del backend
│
└── deploy_frontend/       <- Copia suelta de index.html, solo para Netlify Drop
    └── index.html
```

`frontend/index.html` y `deploy_frontend/index.html` son el mismo archivo.
Se mantienen separados porque Netlify Drop necesita el `index.html` solo,
sin subcarpetas.

## Para correr en tu PC (Docker)

```bash
cd product-analyzer
cp .env.example .env
# completá tus credenciales reales en .env
docker-compose up --build
```

API en `http://localhost:8000`. Dashboard: abrí `frontend/index.html` en el navegador.

## Para subir a GitHub

```bash
cd proyecto-completo
git init
git add .
git commit -m "Proyecto inicial: backend + frontend + landing"
git branch -M main
git remote add origin https://github.com/TU_USUARIO/TU_REPO.git
git push -u origin main
```

Reemplazá `TU_USUARIO/TU_REPO` por el repositorio que crees en GitHub.
El `.gitignore` ya excluye el `.env` real, así que tus credenciales no se suben.

## Para publicar el frontend en Netlify

Arrastrá la carpeta `deploy_frontend/` (o el `index.html` de adentro) a
Netlify Drop, o conectá el repo de GitHub y configurá `deploy_frontend`
como carpeta de publicación.
