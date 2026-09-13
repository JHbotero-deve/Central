# 🚀 Radar de Producto: AI-Driven Fashion Analyzer

**Radar de Producto** es una plataforma de inteligencia de mercado diseñada para detectar oportunidades de arbitraje y monetización en el sector de la moda. El sistema rastrea en tiempo real las tres plataformas más grandes del mundo: **Mercado Libre**, **Amazon** y **TikTok Shop**.

## 💰 Modelo de Generación de Ingresos

Este proyecto no es solo una herramienta técnica, es una máquina de monetización basada en tres pilares:

1.  **Afiliación Inteligente:** El sistema detecta productos con alta demanda y bajo precio, generando enlaces de afiliado automáticos.
2.  **Dropshipping Optimizado:** Calcula el margen real entre el costo del proveedor y el precio de venta sugerido, identificando productos "Legendarios".
3.  **SaaS de Datos:** El dashboard puede ser ofrecido como suscripción para otros vendedores que busquen saber qué productos importar o vender.

## ✨ Características Principales

-   **Scoring de Oportunidad:** Algoritmo propio que combina precio relativo, volumen de ventas y tendencia para asignar una "Rareza" (Común, Rara, Épica, Legendaria).
-   **Visualización 3D:** Integración de modelos GLB/glTF y visor genérico basado en Three.js para inspeccionar la calidad del producto sin salir de la web.
-   **Alertas en Tiempo Real:** Notificaciones instantáneas vía Telegram cuando un producto supera el umbral de oportunidad.
-   **Comparador Multi-Plataforma:** Análisis lado a lado del mismo producto en diferentes mercados para detectar el mejor margen.

## 🛠️ Stack Tecnológico

-   **Backend:** Python 3.11 + FastAPI (Alta performance).
-   **Base de Datos:** PostgreSQL 16 (Relacional, robusta).
-   **Frontend:** HTML5 / CSS3 / JavaScript (Vanilla) + Three.js (Modelado 3D).
-   **Infraestructura:** Docker & Docker Compose.
-   **Despliegue sugerido:** Railway.app (Backend) & Netlify (Frontend).

## 🚀 Guía de Inicio Rápido

### Local (Desarrollo)
1. Clonar el repo.
2. Crear archivo .env basado en .env.example.
3. Ejecutar:
   \\\ash
   docker compose up --build -d
   \\\
4. Acceder a la interfaz en http://localhost:3000.

### Cloud (Producción)
1. **Backend:** Conectar repositorio a **Railway.app** y configurar las variables de entorno.
2. **Frontend:** Conectar repositorio a **Netlify** y actualizar la API_BASE en index.html con la URL de Railway.

## 📜 Licencia
Propiedad privada. Todos los derechos reservados.
