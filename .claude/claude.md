# Instrucciones para Claude / asistentes de IA — ActivosPALDACA

## Obligatorio antes de escribir código

1. Leer **`docs/IA_CONTEXT.md`**.
2. Según la tarea, consultar:
   - `docs/ARCHITECTURE.md`
   - `docs/BUSINESS_RULES.md`
   - `docs/INTEGRATION.md`
3. Solo después, explorar el código afectado e implementar.

## Qué es este repo

Satélite **Gestión de Activos** (`MODULO_CODIGO = activos`). Django server-rendered. Inventario, asignaciones, mantenimientos, PDFs. El login está en **Portal-Paldaca** (SSO).

## Reglas duras

- No implementar login local; usar SSO Portal (`paldaca_sessionid`).
- No duplicar ni alterar migraciones `core_*` sin alinear con Portal.
- Tablas de negocio con prefijo **`activos_`**.
- Misma `DJANGO_SECRET_KEY` y MySQL que Portal.
- Respetar reglas de `docs/BUSINESS_RULES.md` (p. ej. superusuarios no reciben activos).
- Gate de acceso: `tiene_acceso_modulo("activos")` / `@requiere_modulo_paldaca`.

## Orden de lectura por tarea

| Tarea | Leer primero |
|-------|----------------|
| CRUD activos / historial | `IA_CONTEXT` → `BUSINESS_RULES` → `activos/` |
| Mantenimientos | `IA_CONTEXT` → `BUSINESS_RULES` → `mantenimientos/` |
| SSO / nav Portal | `INTEGRATION` → `core/middleware.py`, context processors |
| Usuarios UI | `BUSINESS_RULES` → `usuarios/` |
