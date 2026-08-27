# Contexto IA — ActivosPALDACA (SSAPI)

> Resumen condensado para asistentes (Cursor, Claude Code, ChatGPT). Derivar detalle de `docs/ARCHITECTURE.md`, `docs/BUSINESS_RULES.md`, `docs/INTEGRATION.md`.

---

## Objetivo del repositorio

Módulo **Gestión de Activos** de PALDACA Suite. Django server-rendered en `activos.cpaldaca.com`. Inventario, asignaciones, mantenimientos, PDFs. **No** es el portal de login.

---

## Stack

- Django **5.2.7**, MySQL (`mysqlclient`), ReportLab PDF
- Templates + Bootstrap 5 + `activos-ui.js`
- Tests: pytest-django, SQLite memoria (`SSAPI/settings_test.py`)
- Config: `key.env` (+ `dev.env` local) — **misma SECRET_KEY y MySQL que Portal-Paldaca**

---

## Apps

| App | Rol |
|-----|-----|
| `core` | `UsuarioPaldaca`, SSO middleware, home, errores, nav embed |
| `activos` | Dominio: categorías, activos, historial |
| `mantenimientos` | Mantenimientos → sync estado activo |
| `reportes` | PDF (ReportLab); modelo `ReporteGenerado` sin uso en vistas |
| `usuarios` | UI personas sobre `core_usuario`; `models.py` vacío |

Proyecto Django: **`SSAPI/`**. Entry: `manage.py`.

---

## Modelos clave

**Compartidos (`core_*`):** `UsuarioPaldaca`, `Modulo`, `UsuarioModulo`, `Disciplina`, `Perfil`

**Negocio (`activos_*`):** `Categoria`, `SubCategoria` (prefijo único), `Ubicacion`, `Activo`, `HistorialMovimiento`, `EtiquetaQR`, `Mantenimiento`, `ReporteGenerado`

**Activo:** FK `subcategoria`, `ubicacion`, `usuario_asignado` → `core.UsuarioPaldaca`. Estados: `AC/IN/EM`. Código auto: `PAL-{PREFIJO}-NNN`.

**EtiquetaQR:** etiqueta física. `token` opaco (12 chars, va en el QR), `codigo_reservado`, FK `subcategoria`, FK `activo` (null). Estados `PE/VI/AN`.
El código se reserva **al imprimir**, antes de que exista el activo — por eso es tabla propia y no un campo de `Activo`.

---

## Auth y acceso

```python
AUTH_USER_MODEL = "core.UsuarioPaldaca"
MODULO_CODIGO = "activos"  # activos/constants.py
```

- SSO: cookie `paldaca_sessionid`, `DJANGO_SECRET_KEY` compartida
- Login/logout → Portal (`PALDACA_SSO_LOGIN_URL`, `PALDACA_SSO_LOGOUT_URL`)
- Guard: `ModuloActivoRequiredMixin`, `@requiere_modulo_paldaca` → `tiene_acceso_modulo("activos")`
- `PaldacaSessionMiddleware`: invalida sesión si cambian permisos (`get_auth_revision`)
- **`es_administrador_en_modulo()` no se usa en vistas** — acceso binario al módulo
- **Excepción anónima:** `/q/<token>/` (ficha pública de una etiqueta QR) es la ÚNICA vista sin sesión.
  Vive aislada en `activos/views_publicos.py`. Publica datos del equipo + nombre y apellido del responsable; nada más.

---

## Flujo principal

1. Request → session cookie → auth → middleware revisión → decorador módulo
2. `/activos/` listado con filtros; CRUD catálogos y activos
3. Reasignar/reubicar → `HistorialMovimiento` (tipos `RE`, `RU`)
4. Mantenimiento `EP` → activo `EM`; último `FI` → activo `AC`
5. `/reportes/activos/` PDF con mismos filtros GET

---

## Reglas de negocio críticas

- Superusuarios **no** reciben activos (`activos/models.py`, `activos/forms.py`)
- Estado UI derivado: `AC`+sin user = Disponible; `AC`+user = Asignado (`activo_filters.py`)
- No borrar `core_usuario` — solo `is_active=False` (`usuarios/views.py`)
- No desactivar usuario con activos asignados
- Categoría/subcategoría/ubicación: no delete si tienen hijos/activos
- Crear usuario desde Activos → `set_unusable_password()`, **sin** auto-asignar `UsuarioModulo`

---

## Integraciones Suite

| Con | Cómo |
|-----|------|
| Portal-Paldaca | SSO, logout API, `paldaca-nav.js/css`, API menú |
| MySQL compartido | `core_*` + `activos_*` + `django_session` |
| Calidad/Codigos/HDT | Solo vía BD compartida (`core_*`), sin imports |

Nav: `core/context_processors.py` → `paldaca_nav_current_app = "activos"`.

---

## Convenciones

- Tablas negocio: prefijo `activos_` via `TABLA()` en `activos/constants.py`
- CBV Django + algunas FBV (reasignar, acciones masivas)
- Mensajes persona: `get_full_name()`, nunca username (`_nombre()`, `nombre_completo` filter)
- CSS namespace `.ax-*` en `activos/static/css/activos-ui.css`
- Delete views: POST only; GET redirige (`SinPaginaDeBorradoMixin`)

---

## Archivos críticos

```
SSAPI/settings.py          # SSO, BD, middleware, handlers error
SSAPI/db.py                # DATABASEDES / DATABASEPROD
SSAPI/urls.py              # Rutas raíz
core/models.py             # UsuarioPaldaca, permisos módulo
core/middleware.py         # PaldacaSessionMiddleware
core/context_processors.py # URLs nav Portal
activos/models.py          # Dominio inventario
activos/views.py           # Lógica principal + historial
activos/decorators.py      # Guard módulo
activos/constants.py       # MODULO_CODIGO, TABLA()
activos/services/codigos.py # Reserva de codigo_inventario (único punto, con bloqueo)
activos/services/qr.py      # Generación de QR (segno) y URL pública
activos/views_publicos.py   # Ficha anónima /q/<token>/
activos/views_etiquetas.py  # Gestión de etiquetas (protegida)
reportes/services/etiquetas.py # Hoja Avery 5160 sobre Letter
activos/forms.py           # Validaciones asignación
activos/templatetags/activo_filters.py  # Estado derivado UI
key.env.example            # Plantilla env SSO
```

---

## URLs principales

| Ruta | Nombre |
|------|--------|
| `/` | `core:home` |
| `/activos/` | `activos:activo-list` |
| `/activos/crear/` | `activos:activo-create` |
| `/activos/etiquetas/` | `activos:etiqueta-list` |
| `/q/<token>/` | `etiqueta-publica` (**anónima**, sin namespace) |
| `/q/<token>/alta/` | `etiqueta-alta` (SSO; bajo `/q/` para heredar su exclusión del shell) |
| `/reportes/etiquetas/` | `reportes:etiquetas-pdf` |
| `/mantenimientos/` | `mantenimientos:mantenimiento-list` |
| `/reportes/activos/` | `reportes:reporte-activos` |
| `/usuarios/` | `usuarios:usuario-search` |
| `/admin/` | Django admin |

---

## Riesgos conocidos

1. `README.md` obsoleto (dice PostgreSQL/SQLite; código usa MySQL)
2. `psycopg2-binary` en requirements sin uso (Pillow SÍ es necesario: ReportLab lo usa para el logo PNG; se añadió en la rama rework-QR)
3. Rol administrador no enforced en vistas Activos
4. `ReporteGenerado` no persistido al generar PDF
5. Alta usuario en Activos no crea `UsuarioModulo` → puede quedar sin acceso
6. Migraciones `core` deben stay synced con Portal-Paldaca (**hoy Activos solo tiene hasta `0010`; faltan `0011`/`0013`**)
7. `base.js` referencia `/ia/chat/api/` inexistente en urls
8. `seed_core_modulos` vs migración `0006` — catálogo módulos puede diferir
9. Sesión: configurar AGE/EXPIRE/SAVE alineados al Portal (hoy defaults Django)
10. Puerto oficial Suite: **8001** (no 8004)

---

## Comandos útiles

```bash
python manage.py migrate
python manage.py seed_core_modulos
python manage.py seed_activos_pal          # datos demo
python manage.py etiquetar_activos --dry-run  # etiquetas QR para inventario existente
pytest                                      # SSAPI/settings_test
python manage.py runserver 8001            # puerto oficial Suite (Portal .env.development)
```

---

## Al implementar cambios

- **No** duplicar tablas `core_*` ni otro `AUTH_USER_MODEL`
- Proteger vistas nuevas con `ModuloActivoRequiredMixin` o `@requiere_modulo_paldaca`
- Nuevas tablas negocio: prefijo `activos_`
- FK a usuario: siempre `settings.AUTH_USER_MODEL`
- Cambios en permisos globales: considerar impacto en `get_auth_revision()` y SSO Suite
- No implementar login local; usar `PALDACA_SSO_LOGIN_URL`

---

## Estado vs documentación legacy

- App `mantenimientos` y `reportes`: **implementadas** (README raíz dice "pendiente" — incorrecto)
- App `usuarios`: gestiona `core.UsuarioPaldaca`, no `UsuarioAsignado` (eliminado)
