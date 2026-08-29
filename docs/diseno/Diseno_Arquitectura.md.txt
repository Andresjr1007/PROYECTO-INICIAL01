# Fase 02: Diseño del Sistema

## 1. Arquitectura
El sistema sigue un patrón **MVC (Modelo-Vista-Controlador)**:
- **Modelo:** Archivo `database.py` (gestión de datos, tablas y consultas).
- **Vista:** Carpeta `templates/` (HTML), `static/` (CSS y JS).
- **Controlador:** Archivo `app.py` (lógica de negocio y rutas).

## 2. Diseño de Base de Datos
Las tablas principales son: **Usuarios, Categorías, Tickets, Historial** y **Adjuntos**.
El esquema relacional completo está documentado en `schema_postgresql.sql`.

## 3. Diseño de Interfaz (UI)
- Interfaz **responsive** (adaptable a móviles y escritorio).
- Página de login/registro, panel de administración, listado de tickets y vista de detalle.
- Menú público y menú interno privado según el rol del usuario.