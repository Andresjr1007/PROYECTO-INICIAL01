# Fase 01: Análisis de Requisitos

## 1. Análisis de Actores
- **Administrador:** Gestiona usuarios, categorías, tickets y reportes.
- **Agente:** Recibe y resuelve tickets asignados.
- **Cliente:** Crea tickets y consulta el estado de sus solicitudes.

## 2. Requerimientos priorizados (Análisis de valor)
- **Prioridad Alta:** Autenticación segura, creación de tickets, asignación de agentes.
- **Prioridad Media:** Exportación de reportes en PDF/Excel, historial de tickets.
- **Prioridad Baja:** Implementación de IA para sugerencias o clasificación.

## 3. Viabilidad Técnica
- Backend en Python con Flask (ligero y robusto).
- Base de datos SQLite local (fácil de ejecutar sin servicios externos), con esquema diseñado para migrar a PostgreSQL.
- Frontend con HTML5, CSS3 y JavaScript vanilla.