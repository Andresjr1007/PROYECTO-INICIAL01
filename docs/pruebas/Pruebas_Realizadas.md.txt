# Fase 04: Pruebas del Sistema

## 1. Estrategia de Pruebas
Se realizaron pruebas funcionales manuales (smoke testing) para validar los flujos críticos del sistema.

## 2. Casos de Prueba Ejecutados
- **CP-01:** Login de administrador (Resultado: Éxito).
- **CP-02:** Login de cliente (Resultado: Éxito).
- **CP-03:** Crear una solicitud/ticket (Resultado: Éxito).
- **CP-04:** Visualizar detalle del ticket (Resultado: Éxito).
- **CP-05:** Acceso a dashboard, usuarios y categorías (Resultado: Éxito).
- **CP-06:** Exportación de reportes en PDF y Excel (Resultado: Éxito).

## 3. Observaciones
Los flujos funcionan correctamente. Se recomienda en una versión futura implementar pruebas automatizadas con `pytest`.