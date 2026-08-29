# Portal de atención al cliente

**Creador del proyecto:** Andres Felipe Figueroa

Aplicación web funcional para registrar, asignar, responder y cerrar solicitudes de clientes.

## Qué incluye

- Registro de clientes y autenticación por roles.
- Flujo de tickets con estados, historial y comentarios.
- Adjuntos para solicitudes.
- Panel de administración con usuarios y categorías.
- Dashboard con KPI.
- Reportes mensuales en PDF y Excel.
- Página adicional con la propuesta de implementación de Inteligencia Artificial.

## Credenciales demo

- Administrador: `admin@portal.local` / `Admin123!`
- Empleado: `agente@portal.local` / `Agente123!`
- Cliente: `cliente@portal.local` / `Cliente123!`

## Cómo ejecutar

1. Abre una terminal en `C:\Users\andre\source\repos\portal-atencion-cliente`.
2. Ejecuta:

```powershell
& 'C:\Users\andre\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' app.py
```

3. Abre `http://127.0.0.1:5000`.

## Persistencia

- La aplicación usa SQLite local en `data\portal.db` para quedar operativa sin configuración adicional.
- El modelo está pensado para migrarse a PostgreSQL y se incluye un esquema de referencia en `schema_postgresql.sql`.

## Exportaciones

- Los reportes mensuales se descargan en PDF y Excel desde la sección de administración.

## Propuesta IA

La evolución del portal incluye una sección pública en `/propuesta-ia` donde se resume la propuesta
de Inteligencia Artificial: clasificación automática, priorización, resúmenes, recomendaciones,
chat de apoyo y análisis histórico con supervisión humana.
